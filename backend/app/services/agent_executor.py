"""Tool Executor: the single choke point that may run a tool handler.

Order of checks for every invocation:
  forbidden arguments -> schema validation -> policy (identity, membership,
  allowlist, permission, approval, state) -> handler with timeout -> output
  validation and bounding.
No code path in the runtime calls ``ToolSpec.handler`` except this module.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_logging import log_event
from app.core.agent_state import AgentRunStatus
from app.core.workspace_role import AuditOutcome
from app.models.agent import AgentApprovalRequest, AgentRun, AgentStep
from app.services.agent_audit import audit_agent_event
from app.services.agent_policy import (
    AgentPolicy,
    PolicyDecision,
    find_forbidden_argument_keys,
)
from app.services.agent_tools import ToolContext, ToolError, ToolSpec

logger = logging.getLogger(__name__)


class OutcomeKind(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    DENIED = "denied"
    NEEDS_APPROVAL = "needs_approval"


@dataclass(slots=True)
class ToolOutcome:
    kind: OutcomeKind
    result: dict[str, Any] | None = None
    code: str | None = None
    message: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    validated_arguments: dict[str, Any] | None = None
    decision: PolicyDecision | None = None


def bound_result(result: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    serialized = json.dumps(result, default=str, ensure_ascii=False)
    if len(serialized.encode("utf-8")) <= max_bytes:
        return result
    return {
        "truncated": True,
        "preview": serialized[: max(0, max_bytes // 2)],
    }


class ToolExecutor:
    def __init__(self, *, policy: AgentPolicy | None = None, max_result_bytes: int) -> None:
        self.policy = policy or AgentPolicy()
        self.max_result_bytes = max_result_bytes

    async def invoke(
        self,
        session: AsyncSession,
        *,
        run: AgentRun,
        step: AgentStep,
        spec: ToolSpec,
        raw_arguments: dict[str, Any],
        expected_run_status: AgentRunStatus = AgentRunStatus.RUNNING,
        approval: AgentApprovalRequest | None = None,
    ) -> ToolOutcome:
        # Cache scalars before any rollback or commit to prevent MissingGreenlet
        run_id: UUID = run.id
        workspace_id: UUID = run.workspace_id
        actor_id: UUID = run.initiated_by
        correlation_id: str | None = run.correlation_id
        step_id: UUID = step.id
        step_index: int = step.step_index
        idempotency_key: str = step.idempotency_key

        base_details = {
            "run_id": run_id,
            "step_id": step_id,
            "step_index": step_index,
            "tool": spec.name,
            "side_effect": spec.side_effect.value,
            "permission": spec.required_permission.value,
            "initiated_by": actor_id,
            "correlation_id": correlation_id,
        }

        forbidden = find_forbidden_argument_keys(raw_arguments)
        if forbidden:
            await self._audit_denied(session, workspace_id, actor_id, run_id, "forbidden_argument", base_details)
            return ToolOutcome(
                OutcomeKind.DENIED,
                code="forbidden_argument",
                message=(
                    "Arguments may not include identity, tenancy or approval fields: "
                    + ", ".join(forbidden)
                ),
            )

        try:
            validated = spec.input_model.model_validate(raw_arguments)
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
            return ToolOutcome(
                OutcomeKind.FAILED,
                code="invalid_arguments",
                message="Invalid arguments for fields: " + ", ".join(fields)[:200],
            )
        arguments = validated.model_dump(mode="json")

        decision = await self.policy.authorize_invocation(
            session,
            run=run,
            step=step,
            spec=spec,
            expected_run_status=expected_run_status,
            approval=approval,
        )
        if not decision.allowed:
            await self._audit_denied(session, workspace_id, actor_id, run_id, decision.code, base_details)
            return ToolOutcome(
                OutcomeKind.DENIED,
                code=decision.code,
                message=decision.message,
                decision=decision,
                validated_arguments=arguments,
            )

        if decision.requires_approval:
            return ToolOutcome(
                OutcomeKind.NEEDS_APPROVAL,
                code=decision.code,
                decision=decision,
                validated_arguments=arguments,
            )

        ctx = ToolContext(
            session=session,
            workspace_id=workspace_id,
            user_id=actor_id,
            run_id=run_id,
            step_id=step_id,
            idempotency_key=idempotency_key,
        )

        try:
            output = await asyncio.wait_for(
                spec.handler(ctx, validated), timeout=spec.timeout_seconds
            )
            validated_output = spec.output_model.model_validate(output)
        except TimeoutError:
            await session.rollback()
            return await self._failure(
                session, workspace_id, actor_id, run_id, base_details, "tool_timeout", "Tool exceeded its time limit"
            )
        except ToolError as exc:
            return await self._failure(
                session, workspace_id, actor_id, run_id, base_details, exc.code, exc.message
            )
        except Exception:  # noqa: BLE001
            await session.rollback()
            log_event(
                logger,
                "agent.tool.unexpected_error",
                level=logging.ERROR,
                run_id=run_id,
                step_id=step_id,
                tool=spec.name,
                exc_info=True,
            )
            return await self._failure(
                session, workspace_id, actor_id, run_id, base_details, "tool_error", "Tool execution failed"
            )

        sources = spec.extract_sources(validated_output)
        result = bound_result(
            validated_output.model_dump(mode="json"), self.max_result_bytes
        )

        audit_details = dict(base_details)
        audit_details["result_count"] = len(sources)
        document_id = result.get("document_id")
        if isinstance(document_id, str):
            audit_details["document_id"] = document_id
        await audit_agent_event(
            session,
            workspace_id=workspace_id,
            action="agent.tool.executed",
            actor_id=actor_id,
            resource_id=run_id,
            details=audit_details,
        )
        log_event(
            logger,
            "agent.tool.executed",
            run_id=run_id,
            step_id=step_id,
            tool=spec.name,
            correlation_id=correlation_id,
        )
        return ToolOutcome(
            OutcomeKind.SUCCESS,
            result=result,
            sources=sources,
            validated_arguments=arguments,
            decision=decision,
        )

    async def _failure(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        actor_id: UUID,
        run_id: UUID,
        details: dict[str, Any],
        code: str,
        message: str,
    ) -> ToolOutcome:
        audit_details = dict(details)
        audit_details["error_code"] = code
        try:
            await audit_agent_event(
                session,
                workspace_id=workspace_id,
                action="agent.tool.failed",
                actor_id=actor_id,
                outcome=AuditOutcome.ERROR,
                resource_id=run_id,
                details=audit_details,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to record failure audit event")
        return ToolOutcome(OutcomeKind.FAILED, code=code, message=message)

    async def _audit_denied(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        actor_id: UUID,
        run_id: UUID,
        reason_code: str,
        details: dict[str, Any],
    ) -> None:
        audit_details = dict(details)
        audit_details["reason_code"] = reason_code
        try:
            await audit_agent_event(
                session,
                workspace_id=workspace_id,
                action="agent.tool.denied",
                actor_id=actor_id,
                outcome=AuditOutcome.DENIED,
                resource_id=run_id,
                details=audit_details,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to record denied audit event")
        log_event(
            logger,
            "agent.tool.denied",
            level=logging.WARNING,
            run_id=run_id,
            step_id=details.get("step_id"),
            tool=details.get("tool"),
            reason_code=reason_code,
            correlation_id=details.get("correlation_id"),
        )
