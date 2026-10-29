"""Agent Runtime Safe Recovery Service (T260028).

Detects stuck agent runs caused by API crashes, worker restarts, or timeouts.
Applies bounded recovery attempts and strictly guards against duplicate side effects.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_state import AgentRunStatus, StepStatus
from app.models.agent import AgentRun
from app.repositories import agent as agent_repo
from app.services.agent_audit import audit_agent_event

logger = logging.getLogger(__name__)


class AgentRecoveryService:
    """Detects and safely recovers stuck or interrupted agent runs."""

    def __init__(self) -> None:
        pass

    async def scan_and_recover_stuck_runs(
        self,
        session: AsyncSession,
        workspace_id: UUID | None = None,
    ) -> list[dict[str, str]]:
        now = datetime.now(UTC)
        stuck_runs = await agent_repo.list_stuck_runs(session, now, workspace_id=workspace_id)
        recovery_summary = []

        for run in stuck_runs:
            result = await self.recover_single_run(session, run, now)
            recovery_summary.append(result)

        return recovery_summary

    async def recover_single_run(
        self,
        session: AsyncSession,
        run: AgentRun,
        now: datetime | None = None,
    ) -> dict[str, str]:
        current_time = now or datetime.now(UTC)
        run_id = run.id
        workspace_id = run.workspace_id

        # Guard 0: Only runs in RUNNING state are eligible for recovery
        if run.status != AgentRunStatus.RUNNING.value:
            return {"run_id": str(run_id), "action": "ignored_not_running"}

        # Guard 1: Deadline timeout check
        if run.deadline_at and current_time >= run.deadline_at:
            await agent_repo.transition_run(
                session,
                run_id=run_id,
                expected=AgentRunStatus.RUNNING,
                target=AgentRunStatus.FAILED,
                reason="Run execution budget timed out",
                error_code="execution_timeout",
                error_message="Agent run deadline exceeded during execution",
            )
            await agent_repo.append_event(
                session,
                run_id=run_id,
                workspace_id=workspace_id,
                event_type="run_failed",
                data={"error_code": "execution_timeout", "reason": "deadline_exceeded"},
            )
            await audit_agent_event(
                session,
                workspace_id=workspace_id,
                action="agent.run.recovered_failed",
                actor_id=run.initiated_by,
                resource_id=run_id,
                details={"reason": "deadline_timeout"},
            )
            logger.warning("Stuck run %s marked FAILED due to deadline timeout", run_id)
            return {"run_id": str(run_id), "action": "failed_timeout"}

        # Guard 2: Max recovery attempts reached
        if run.recovery_attempts >= run.max_recovery_attempts:
            await agent_repo.transition_run(
                session,
                run_id=run_id,
                expected=AgentRunStatus.RUNNING,
                target=AgentRunStatus.FAILED,
                reason="Max recovery attempts exceeded",
                error_code="max_recovery_attempts_exceeded",
                error_message=f"Agent run failed after {run.recovery_attempts} recovery attempts",
            )
            await agent_repo.append_event(
                session,
                run_id=run_id,
                workspace_id=workspace_id,
                event_type="run_failed",
                data={"error_code": "max_recovery_attempts_exceeded"},
            )
            logger.warning(
                "Stuck run %s marked FAILED after exhausting max recovery attempts (%d/%d)",
                run_id,
                run.recovery_attempts,
                run.max_recovery_attempts,
            )
            return {"run_id": str(run_id), "action": "failed_max_attempts"}

        # Guard 3: Inspect active step for duplicate WRITE side-effects
        steps = await agent_repo.list_steps(session, run_id)
        if steps:
            last_step = steps[-1]
            if (
                last_step.status == StepStatus.PENDING.value
                and last_step.side_effect == "WRITE"
            ):
                # Strictly prevent duplicate mutation: fail interrupted step and fail run closed
                await agent_repo.finish_step(
                    session,
                    last_step.id,
                    status=StepStatus.FAILED,
                    error_code="execution_interrupted",
                    error_message="Step execution was interrupted by process failure; safely terminated to prevent duplicate mutation",
                )
                await agent_repo.append_event(
                    session,
                    run_id=run_id,
                    workspace_id=workspace_id,
                    event_type="step_failed",
                    step_id=last_step.id,
                    data={"reason": "interrupted_write_prevented"},
                )
                await agent_repo.transition_run(
                    session,
                    run_id=run_id,
                    expected=AgentRunStatus.RUNNING,
                    target=AgentRunStatus.FAILED,
                    reason="Cannot safely resume run after unconfirmed mutation",
                    error_code="unconfirmed_mutation",
                    error_message="Agent run interrupted during WRITE step; failed closed to prevent duplicate mutation",
                )
                await agent_repo.append_event(
                    session,
                    run_id=run_id,
                    workspace_id=workspace_id,
                    event_type="run_failed",
                    data={"error_code": "unconfirmed_mutation", "reason": "interrupted_write_prevented"},
                )
                await audit_agent_event(
                    session,
                    workspace_id=workspace_id,
                    action="agent.run.recovered_failed",
                    actor_id=run.initiated_by,
                    resource_id=run_id,
                    details={"reason": "interrupted_write_prevented"},
                )
                logger.warning("Stuck run %s marked FAILED to prevent duplicate WRITE mutation", run_id)
                return {"run_id": str(run_id), "action": "failed_unconfirmed_mutation"}

        # Increment recovery attempt and release stale lease
        attempts = await agent_repo.increment_recovery_attempt(session, run_id)
        await agent_repo.release_run_lease(session, run_id, lease_token=run.lease_token or "")

        await agent_repo.append_event(
            session,
            run_id=run_id,
            workspace_id=workspace_id,
            event_type="run_recovery_attempted",
            data={"attempt": attempts, "max_attempts": run.max_recovery_attempts},
        )
        await audit_agent_event(
            session,
            workspace_id=workspace_id,
            action="agent.run.recovery_attempted",
            actor_id=run.initiated_by,
            resource_id=run_id,
            details={"attempt": attempts},
        )
        logger.info("Stuck run %s successfully recovered (attempt %d)", run_id, attempts)
        return {"run_id": str(run_id), "action": "recovered_for_execution", "attempt": str(attempts)}
