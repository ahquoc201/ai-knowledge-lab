"""Governed Agent Orchestrator.

Manages execution lifecycle, budget enforcement, step iteration, LLM interaction,
tool execution, and approval pausing.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_state import (
    AgentRunStatus,
    StepStatus,
)
from app.core.config import get_settings
from app.core.workspace_role import AuditOutcome
from app.llm.base import LLMMessage, LLMProvider
from app.models.agent import AgentRun
from app.repositories import agent as agent_repo
from app.services.agent_approval import AgentApprovalService
from app.services.agent_audit import audit_agent_event
from app.services.agent_executor import OutcomeKind, ToolExecutor
from app.services.agent_llm_parser import (
    AgentFinalAnswerDecision,
    AgentToolCallDecision,
    LLMParseError,
    parse_agent_decision,
)
from app.services.agent_prompts import AGENT_SYSTEM_PROMPT, build_agent_prompt
from app.services.agent_tools import ToolRegistry

logger = logging.getLogger(__name__)


class AgentExecutionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AgentOrchestrator:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        executor: ToolExecutor,
        approval_service: AgentApprovalService,
        llm_provider: LLMProvider,
    ) -> None:
        self.registry = registry
        self.executor = executor
        self.approval_service = approval_service
        self.llm_provider = llm_provider
        self.settings = get_settings()

    async def execute_run(self, session: AsyncSession, run_id: UUID) -> AgentRun:
        run = await agent_repo.get_run(session, run_id)
        if not run:
            raise AgentExecutionError("run_not_found", "Agent run not found")

        # Initial transition CREATED -> RUNNING
        if run.status == AgentRunStatus.CREATED.value:
            deadline = datetime.now(UTC) + timedelta(
                seconds=self.settings.agent_run_timeout_seconds
            )
            success = await agent_repo.transition_run(
                session,
                run.id,
                expected=AgentRunStatus.CREATED,
                target=AgentRunStatus.RUNNING,
                deadline_at=deadline,
            )
            if not success:
                run = await agent_repo.get_run(session, run.id)
                return run  # type: ignore

            await agent_repo.append_event(
                session,
                run_id=run.id,
                workspace_id=run.workspace_id,
                event_type="run_started",
                data={"goal": run.goal},
            )
            await audit_agent_event(
                session,
                workspace_id=run.workspace_id,
                action="agent.run.started",
                actor_id=run.initiated_by,
                resource_id=run.id,
                details={"goal": run.goal[:100]},
            )

        target_run_id = run.id
        # Main execution loop
        while True:
            # Re-fetch fresh run state
            run = await agent_repo.get_run(session, target_run_id)
            if not run or run.status != AgentRunStatus.RUNNING.value:
                return run  # Paused, cancelled or completed

            # Check budgets & cancellation
            if run.cancel_requested:
                await self._terminate_run(
                    session, run, AgentRunStatus.CANCELLED, "user_cancelled", "Run cancelled by user"
                )
                return (await agent_repo.get_run(session, run.id))

            now = datetime.now(UTC)
            if run.deadline_at and now >= run.deadline_at:
                await self._terminate_run(
                    session, run, AgentRunStatus.FAILED, "timeout", "Run execution budget timed out"
                )
                return (await agent_repo.get_run(session, run.id))

            if run.current_step >= run.max_steps:
                await self._terminate_run(
                    session, run, AgentRunStatus.FAILED, "step_budget_exceeded", "Maximum execution steps reached"
                )
                return (await agent_repo.get_run(session, run.id))

            if run.tool_call_count >= run.max_tool_calls:
                await self._terminate_run(
                    session, run, AgentRunStatus.FAILED, "tool_budget_exceeded", "Maximum tool calls reached"
                )
                return (await agent_repo.get_run(session, run.id))

            if run.denial_count >= self.settings.agent_max_denials:
                await self._terminate_run(
                    session, run, AgentRunStatus.FAILED, "denial_budget_exceeded", "Too many policy denials"
                )
                return (await agent_repo.get_run(session, run.id))  # Fetch step history for prompt
            db_steps = await agent_repo.list_steps(session, run.id)
            history_data = [
                {
                    "step_index": s.step_index,
                    "tool_name": s.tool_name,
                    "arguments": s.arguments,
                    "status": s.status,
                    "result": s.result,
                    "error_code": s.error_code,
                    "error_message": s.error_message,
                }
                for s in db_steps
            ]

            # Call LLM with bounded retries for structured JSON
            decision = await self._get_llm_decision(run, history_data)
            if not decision:
                await self._terminate_run(
                    session, run, AgentRunStatus.FAILED, "llm_invalid_output", "LLM output schema could not be validated"
                )
                return (await agent_repo.get_run(session, run.id))  # Advance step counter
            await agent_repo.bump_run_counters(session, run.id, steps=1)

            if isinstance(decision, AgentFinalAnswerDecision):
                await self._finish_with_answer(session, run, decision)
                return (await agent_repo.get_run(session, run.id))

            if isinstance(decision, AgentToolCallDecision):
                should_pause = await self._handle_tool_decision(session, run, decision)
                if should_pause:
                    # Paused for human approval or terminal state reached
                    return (await agent_repo.get_run(session, run.id))

        return run

    async def resume_after_approval(
        self, session: AsyncSession, run_id: UUID
    ) -> AgentRun:
        run = await agent_repo.get_run(session, run_id)
        if not run:
            raise AgentExecutionError("run_not_found", "Run not found")

        # If run was AWAITING_APPROVAL, move it back to RUNNING and continue
        if run.status == AgentRunStatus.AWAITING_APPROVAL.value:
            resumed = await agent_repo.transition_run(
                session,
                run.id,
                expected=AgentRunStatus.AWAITING_APPROVAL,
                target=AgentRunStatus.RUNNING,
                reason="Resumed after approval decision",
            )
            if not resumed:
                return run

            await agent_repo.append_event(
                session,
                run_id=run.id,
                workspace_id=run.workspace_id,
                event_type="run_resumed",
            )

        return await self.execute_run(session, run.id)

    async def _get_llm_decision(
        self, run: AgentRun, history: list[dict[str, Any]]
    ) -> AgentToolCallDecision | AgentFinalAnswerDecision | None:
        prompt_content = build_agent_prompt(
            goal=run.goal,
            registry=self.registry,
            allowed_tools=run.allowed_tools,
            step_history=history,
        )

        messages = [
            LLMMessage(role="system", content=AGENT_SYSTEM_PROMPT),
            LLMMessage(role="user", content=prompt_content),
        ]

        retries = self.settings.agent_llm_max_retries
        last_error = ""

        for attempt in range(retries + 1):
            if attempt > 0:
                messages.append(
                    LLMMessage(
                        role="user",
                        content=f"Your previous response had schema error: {last_error}. Please correct it and output valid JSON conforming strictly to the requested schema.",
                    )
                )

            try:
                raw_response = await self.llm_provider.generate(messages)
                decision = parse_agent_decision(raw_response)
                return decision
            except LLMParseError as exc:
                last_error = str(exc)
                logger.warning(
                    "LLM JSON schema parsing failed (attempt %d/%d): %s",
                    attempt + 1,
                    retries + 1,
                    exc,
                )
            except Exception:
                logger.exception("LLM generation error")
                return None

        return None

    async def _handle_tool_decision(
        self,
        session: AsyncSession,
        run: AgentRun,
        decision: AgentToolCallDecision,
    ) -> bool:
        """Execute or queue approval for a tool decision. Returns True if execution loop should pause."""
        spec = self.registry.get(decision.tool_name)
        step_index = run.current_step + 1

        # Check if tool is known
        if not spec:
            step = await agent_repo.create_step(
                session,
                run=run,
                step_index=step_index,
                tool_name=decision.tool_name,
                side_effect=None,
                reason=decision.reason,
                arguments=decision.arguments,
                status=StepStatus.DENIED,
            )
            await agent_repo.finish_step(
                session,
                step.id,
                status=StepStatus.DENIED,
                error_code="tool_not_found",
                error_message=f"Tool `{decision.tool_name}` is not in registry",
            )
            await agent_repo.bump_run_counters(session, run.id, denials=1)
            await agent_repo.append_event(
                session,
                run_id=run.id,
                workspace_id=run.workspace_id,
                event_type="step_denied",
                step_id=step.id,
                data={"reason": f"Tool {decision.tool_name} not found"},
            )
            return False

        # Create step record
        step = await agent_repo.create_step(
            session,
            run=run,
            step_index=step_index,
            tool_name=spec.name,
            side_effect=spec.side_effect.value,
            reason=decision.reason,
            arguments=decision.arguments,
            status=StepStatus.PENDING,
        )

        # Cache IDs to avoid MissingGreenlet if a rollback expires the ORM objects
        step_id = step.id
        run_id = run.id
        workspace_id = run.workspace_id

        await agent_repo.append_event(
            session,
            run_id=run_id,
            workspace_id=workspace_id,
            event_type="step_started",
            step_id=step_id,
            data={"tool": spec.name, "side_effect": spec.side_effect.value},
        )

        # Check execution via ToolExecutor
        outcome = await self.executor.invoke(
            session,
            run=run,
            step=step,
            spec=spec,
            raw_arguments=decision.arguments,
            expected_run_status=AgentRunStatus.RUNNING,
        )

        if outcome.kind == OutcomeKind.NEEDS_APPROVAL:
            # Human approval required: persist approval request and transition run
            assert outcome.validated_arguments is not None
            await self.approval_service.create_approval_request(
                session,
                run=run,
                step=step,
                spec=spec,
                validated_arguments=outcome.validated_arguments,
            )
            await agent_repo.finish_step(
                session, step_id, status=StepStatus.AWAITING_APPROVAL
            )
            await agent_repo.transition_run(
                session,
                run_id,
                expected=AgentRunStatus.RUNNING,
                target=AgentRunStatus.AWAITING_APPROVAL,
                reason="Waiting for human approval",
            )
            return True  # Pause loop

        elif outcome.kind == OutcomeKind.DENIED:
            await agent_repo.finish_step(
                session,
                step_id,
                status=StepStatus.DENIED,
                error_code=outcome.code,
                error_message=outcome.message,
            )
            await agent_repo.bump_run_counters(session, run_id, denials=1)
            await agent_repo.append_event(
                session,
                run_id=run_id,
                workspace_id=workspace_id,
                event_type="step_denied",
                step_id=step_id,
                data={"error_code": outcome.code, "error_message": outcome.message},
            )
            if outcome.decision and outcome.decision.terminal:
                await self._terminate_run(
                    session,
                    run,
                    AgentRunStatus.FAILED,
                    outcome.code or "permission_revoked",
                    outcome.message or "Revocation prevented further execution",
                )
                return True
            return False

        elif outcome.kind == OutcomeKind.SUCCESS:
            await agent_repo.finish_step(
                session,
                step_id,
                status=StepStatus.SUCCEEDED,
                result=outcome.result,
            )
            await agent_repo.bump_run_counters(session, run_id, tool_calls=1)

            # Update accumulated sources on run
            if outcome.sources:
                existing_sources = list(run.sources or [])
                existing_ids = {s.get("document_id") for s in existing_sources}
                for s in outcome.sources:
                    if s.get("document_id") not in existing_ids:
                        existing_sources.append(s)
                await agent_repo.update_run_sources(
                    session,
                    run_id,
                    existing_sources,
                )

            await agent_repo.append_event(
                session,
                run_id=run_id,
                workspace_id=workspace_id,
                event_type="step_succeeded",
                step_id=step_id,
                data={"result": outcome.result},
            )
            return False

        else:  # FAILED
            await agent_repo.finish_step(
                session,
                step_id,
                status=StepStatus.FAILED,
                error_code=outcome.code,
                error_message=outcome.message,
            )
            await agent_repo.append_event(
                session,
                run_id=run_id,
                workspace_id=workspace_id,
                event_type="step_failed",
                step_id=step_id,
                data={"error_code": outcome.code, "error_message": outcome.message},
            )
            return False

    async def _finish_with_answer(
        self,
        session: AsyncSession,
        run: AgentRun,
        decision: AgentFinalAnswerDecision,
    ) -> None:
        await agent_repo.transition_run(
            session,
            run.id,
            expected=AgentRunStatus.RUNNING,
            target=AgentRunStatus.COMPLETED,
            final_answer=decision.answer,
        )
        await agent_repo.append_event(
            session,
            run_id=run.id,
            workspace_id=run.workspace_id,
            event_type="run_completed",
            data={"final_answer": decision.answer, "citations": decision.citations},
        )
        await audit_agent_event(
            session,
            workspace_id=run.workspace_id,
            action="agent.run.completed",
            actor_id=run.initiated_by,
            resource_id=run.id,
            details={"step_count": run.current_step},
        )

    async def _terminate_run(
        self,
        session: AsyncSession,
        run: AgentRun,
        target_status: AgentRunStatus,
        error_code: str,
        message: str,
    ) -> None:
        current_status = AgentRunStatus(run.status)
        await agent_repo.transition_run(
            session,
            run.id,
            expected=current_status,
            target=target_status,
            error_code=error_code,
            error_message=message,
        )
        await agent_repo.append_event(
            session,
            run_id=run.id,
            workspace_id=run.workspace_id,
            event_type=f"run_{target_status.value}",
            data={"error_code": error_code, "error_message": message},
        )
        await audit_agent_event(
            session,
            workspace_id=run.workspace_id,
            action=f"agent.run.{target_status.value}",
            actor_id=run.initiated_by,
            outcome=AuditOutcome.DENIED if target_status == AgentRunStatus.CANCELLED else AuditOutcome.ERROR,
            resource_id=run.id,
            details={"error_code": error_code},
        )
