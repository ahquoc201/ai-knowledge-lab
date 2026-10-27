"""Human-in-the-loop approval service for the Governed Agent Runtime."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_state import (
    AgentRunStatus,
    ApprovalStatus,
    StepStatus,
)
from app.core.config import get_settings
from app.core.workspace_role import AuditOutcome
from app.models.agent import AgentApprovalRequest, AgentRun, AgentStep
from app.models.user import User
from app.repositories import agent as agent_repo
from app.services.agent_audit import audit_agent_event
from app.services.agent_executor import OutcomeKind, ToolExecutor
from app.services.agent_policy import compute_payload_hash, fresh_membership
from app.services.agent_tools import ToolRegistry, ToolSpec
from app.services.rbac import has_permission

logger = logging.getLogger(__name__)


class ApprovalError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AgentApprovalService:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        executor: ToolExecutor,
    ) -> None:
        self.registry = registry
        self.executor = executor
        self.settings = get_settings()

    async def create_approval_request(
        self,
        session: AsyncSession,
        *,
        run: AgentRun,
        step: AgentStep,
        spec: ToolSpec,
        validated_arguments: dict[str, Any],
    ) -> AgentApprovalRequest:
        payload = {
            "run_id": str(run.id),
            "step_id": str(step.id),
            "workspace_id": str(run.workspace_id),
            "tool": spec.name,
            "action": f"Execute {spec.name}",
            "arguments": validated_arguments,
            "impact": spec.describe_impact(spec.input_model.model_validate(validated_arguments)),
            "required_permission": spec.required_permission.value,
        }
        payload_hash = compute_payload_hash(payload)
        expires_at = datetime.now(UTC) + timedelta(
            seconds=self.settings.agent_approval_ttl_seconds
        )

        approval = await agent_repo.create_approval(
            session,
            run=run,
            step=step,
            tool_name=spec.name,
            payload=payload,
            payload_hash=payload_hash,
            expires_at=expires_at,
        )

        await agent_repo.append_event(
            session,
            run_id=run.id,
            workspace_id=run.workspace_id,
            event_type="approval_requested",
            step_id=step.id,
            data={
                "approval_id": str(approval.id),
                "tool": spec.name,
                "impact": payload["impact"],
                "expires_at": expires_at.isoformat(),
            },
        )

        await audit_agent_event(
            session,
            workspace_id=run.workspace_id,
            action="agent.approval.requested",
            actor_id=run.initiated_by,
            resource_id=approval.id,
            details={
                "run_id": run.id,
                "step_id": step.id,
                "tool": spec.name,
                "payload_hash": payload_hash,
            },
        )

        return approval

    async def approve_request(
        self,
        session: AsyncSession,
        *,
        approval_id: UUID,
        approver: User,
        workspace_id: UUID,
        reason: str | None = None,
    ) -> tuple[AgentApprovalRequest, AgentStep]:
        approval = await agent_repo.get_approval(session, approval_id)
        if approval is None or approval.workspace_id != workspace_id:
            raise ApprovalError("approval_not_found", "Approval request not found in workspace")

        if approval.status != ApprovalStatus.PENDING.value:
            raise ApprovalError("invalid_approval_status", f"Approval request is already {approval.status}")

        now = datetime.now(UTC)
        if approval.expires_at <= now:
            await agent_repo.advance_approval(
                session, approval.id, expected=ApprovalStatus.PENDING, target=ApprovalStatus.EXPIRED
            )
            raise ApprovalError("approval_expired", "Approval request has expired")

        # Check approver permission in the workspace
        approver_membership = await fresh_membership(
            session, workspace_id=workspace_id, user_id=approver.id
        )
        if not approver_membership:
            raise ApprovalError("approver_unauthorized", "Approver is not a member of the workspace")

        spec = self.registry.get(approval.tool_name)
        if not spec:
            raise ApprovalError("tool_not_found", f"Tool {approval.tool_name} is not registered")

        if not has_permission(approver_membership.role, spec.required_permission):
            await audit_agent_event(
                session,
                workspace_id=workspace_id,
                action="agent.approval.denied",
                actor_id=approver.id,
                outcome=AuditOutcome.DENIED,
                resource_id=approval.id,
                details={
                    "reason_code": "approver_missing_permission",
                    "permission": spec.required_permission.value,
                    "tool": spec.name,
                },
            )
            raise ApprovalError(
                "permission_denied",
                f"Approver lacks required permission: {spec.required_permission.value}",
            )

        # Atomic transition to APPROVED
        claimed = await agent_repo.claim_approval_decision(
            session,
            approval_id=approval.id,
            decision=ApprovalStatus.APPROVED,
            decided_by=approver.id,
            reason=reason,
        )
        if not claimed:
            raise ApprovalError("approval_conflict", "Approval was already decided or expired")

        await audit_agent_event(
            session,
            workspace_id=workspace_id,
            action="agent.approval.approved",
            actor_id=approver.id,
            resource_id=approval.id,
            details={
                "run_id": approval.run_id,
                "step_id": approval.step_id,
                "tool": approval.tool_name,
                "payload_hash": approval.payload_hash,
            },
        )

        run = await agent_repo.get_run(session, approval.run_id)
        step = await agent_repo.get_step(session, approval.step_id)
        if not run or not step:
            raise ApprovalError("corrupted_state", "Associated run or step not found")

        # Execute approved tool
        return await self._execute_approved_action(
            session, run=run, step=step, approval=approval, spec=spec
        )

    async def reject_request(
        self,
        session: AsyncSession,
        *,
        approval_id: UUID,
        approver: User,
        workspace_id: UUID,
        reason: str | None = None,
    ) -> AgentApprovalRequest:
        approval = await agent_repo.get_approval(session, approval_id)
        if approval is None or approval.workspace_id != workspace_id:
            raise ApprovalError("approval_not_found", "Approval request not found in workspace")

        if approval.status != ApprovalStatus.PENDING.value:
            raise ApprovalError("invalid_approval_status", f"Approval request is already {approval.status}")

        approver_membership = await fresh_membership(
            session, workspace_id=workspace_id, user_id=approver.id
        )
        if not approver_membership:
            raise ApprovalError("approver_unauthorized", "Approver is not a member of the workspace")

        claimed = await agent_repo.claim_approval_decision(
            session,
            approval_id=approval.id,
            decision=ApprovalStatus.REJECTED,
            decided_by=approver.id,
            reason=reason,
        )
        if not claimed:
            raise ApprovalError("approval_conflict", "Approval was already decided or expired")

        step = await agent_repo.get_step(session, approval.step_id)
        if step:
            await agent_repo.finish_step(
                session,
                step.id,
                status=StepStatus.REJECTED,
                error_code="approval_rejected",
                error_message=reason or "Action was rejected by user",
            )

        run = await agent_repo.get_run(session, approval.run_id)
        if run and run.status == AgentRunStatus.AWAITING_APPROVAL.value:
            # Transition back to RUNNING or COMPLETED depending on retry/finish logic
            # A rejection pauses or moves the agent forward with an error step
            await agent_repo.transition_run(
                session,
                run.id,
                expected=AgentRunStatus.AWAITING_APPROVAL,
                target=AgentRunStatus.RUNNING,
                reason="Approval rejected; agent will handle denial",
            )

        await agent_repo.append_event(
            session,
            run_id=approval.run_id,
            workspace_id=workspace_id,
            event_type="approval_rejected",
            step_id=approval.step_id,
            data={"reason": reason},
        )

        await audit_agent_event(
            session,
            workspace_id=workspace_id,
            action="agent.approval.rejected",
            actor_id=approver.id,
            resource_id=approval.id,
            details={
                "run_id": approval.run_id,
                "step_id": approval.step_id,
                "tool": approval.tool_name,
            },
        )

        return (await agent_repo.get_approval(session, approval_id))  # type: ignore

    async def _execute_approved_action(
        self,
        session: AsyncSession,
        *,
        run: AgentRun,
        step: AgentStep,
        approval: AgentApprovalRequest,
        spec: ToolSpec,
    ) -> tuple[AgentApprovalRequest, AgentStep]:
        # Mark approval as EXECUTING to prevent double execution
        await agent_repo.advance_approval(
            session, approval.id, expected=ApprovalStatus.APPROVED, target=ApprovalStatus.EXECUTING
        )

        raw_arguments = approval.payload.get("arguments", {})

        # ToolExecutor re-validates principal identity, permissions, payload integrity
        outcome = await self.executor.invoke(
            session,
            run=run,
            step=step,
            spec=spec,
            raw_arguments=raw_arguments,
            expected_run_status=AgentRunStatus(run.status),
            approval=approval,
        )
        logger.info("Executed approved tool outcome: %s, code: %s, message: %s", outcome.kind, outcome.code, outcome.message)

        if outcome.kind == OutcomeKind.SUCCESS:
            await agent_repo.advance_approval(
                session, approval.id, expected=ApprovalStatus.EXECUTING, target=ApprovalStatus.EXECUTED
            )
            await agent_repo.finish_step(
                session,
                step.id,
                status=StepStatus.SUCCEEDED,
                result=outcome.result,
            )
            await agent_repo.bump_run_counters(session, run.id, tool_calls=1)
            await agent_repo.append_event(
                session,
                run_id=run.id,
                workspace_id=run.workspace_id,
                event_type="step_succeeded",
                step_id=step.id,
                data={"result": outcome.result},
            )
        else:
            await agent_repo.advance_approval(
                session,
                approval.id,
                expected=ApprovalStatus.EXECUTING,
                target=ApprovalStatus.FAILED,
                reason=outcome.message,
            )
            await agent_repo.finish_step(
                session,
                step.id,
                status=StepStatus.FAILED,
                error_code=outcome.code,
                error_message=outcome.message,
            )
            await agent_repo.append_event(
                session,
                run_id=run.id,
                workspace_id=run.workspace_id,
                event_type="step_failed",
                step_id=step.id,
                data={"error_code": outcome.code, "error_message": outcome.message},
            )

        fresh_approval = await agent_repo.get_approval(session, approval.id)
        fresh_step = await agent_repo.get_step(session, step.id)
        return fresh_approval, fresh_step  # type: ignore
