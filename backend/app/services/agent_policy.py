"""Policy Enforcement for agent tool invocations.

This module is deliberately independent of the LLM. Every decision is derived from
database state that is re-read at decision time (user, membership, approval) and
never from model output. It is invoked by the ToolExecutor for *every* invocation,
including the execution that follows a human approval.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_state import AgentRunStatus, ApprovalStatus
from app.models.agent import AgentApprovalRequest, AgentRun, AgentStep
from app.models.user import User
from app.models.workspace_membership import WorkspaceMembership
from app.services.agent_tools import ToolSpec
from app.services.rbac import has_permission

# Argument names a model must never supply: identity, tenancy and approval state
# are owned by the backend. Presence of any of them is a policy violation.
FORBIDDEN_ARGUMENT_KEYS: frozenset[str] = frozenset(
    {
        "workspace_id",
        "workspace",
        "tenant_id",
        "user_id",
        "initiated_by",
        "role",
        "permission",
        "permissions",
        "approved",
        "approval",
        "approval_id",
        "run_id",
        "step_id",
        "storage_key",
        "path",
        "file_path",
    }
)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    code: str
    message: str = ""
    requires_approval: bool = False
    # A terminal denial means the principal can no longer act at all
    # (membership revoked / account disabled) and the run must stop.
    terminal: bool = False


ALLOW = PolicyDecision(allowed=True, code="allowed")


def compute_payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def find_forbidden_argument_keys(arguments: dict[str, Any]) -> list[str]:
    return sorted(key for key in arguments if key.lower() in FORBIDDEN_ARGUMENT_KEYS)


async def _fresh_user(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(
        select(User).where(User.id == user_id).execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def fresh_membership(
    session: AsyncSession, *, workspace_id: UUID, user_id: UUID
) -> WorkspaceMembership | None:
    """Read membership straight from the database, bypassing the identity map."""
    result = await session.execute(
        select(WorkspaceMembership)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


class AgentPolicy:
    async def authorize_invocation(
        self,
        session: AsyncSession,
        *,
        run: AgentRun,
        step: AgentStep,
        spec: ToolSpec,
        expected_run_status: AgentRunStatus,
        approval: AgentApprovalRequest | None = None,
    ) -> PolicyDecision:
        # 1. Execution state
        if run.status != expected_run_status.value:
            return PolicyDecision(False, "invalid_run_state", "Run is not executable")

        if step.run_id != run.id or step.workspace_id != run.workspace_id:
            return PolicyDecision(False, "step_binding_mismatch", "Step/run mismatch")

        # 2. Authenticated principal bound to the run
        user = await _fresh_user(session, run.initiated_by)
        if user is None or not user.is_active:
            return PolicyDecision(
                False, "principal_inactive", "Initiating user is not active", terminal=True
            )

        # 3. Workspace membership (re-read: revocation must take effect immediately)
        membership = await fresh_membership(
            session, workspace_id=run.workspace_id, user_id=run.initiated_by
        )
        if membership is None:
            return PolicyDecision(
                False,
                "membership_revoked",
                "Initiating user is no longer a workspace member",
                terminal=True,
            )

        # 4. Tool allowlist (fixed at run creation, backend-owned)
        if spec.name not in (run.allowed_tools or []):
            return PolicyDecision(False, "tool_not_allowed", "Tool is not allowlisted")

        # 5. Role-based permission
        if not has_permission(membership.role, spec.required_permission):
            return PolicyDecision(
                False,
                "permission_denied",
                f"Requires {spec.required_permission.value}",
            )

        # 6/7. Approval requirement for side effects
        if spec.requires_approval:
            if approval is None:
                return PolicyDecision(
                    True,
                    "approval_required",
                    "Human approval required",
                    requires_approval=True,
                )
            return self._validate_approval(run=run, step=step, spec=spec, approval=approval)

        return ALLOW

    @staticmethod
    def _validate_approval(
        *,
        run: AgentRun,
        step: AgentStep,
        spec: ToolSpec,
        approval: AgentApprovalRequest,
    ) -> PolicyDecision:
        if (
            approval.run_id != run.id
            or approval.step_id != step.id
            or approval.workspace_id != run.workspace_id
            or approval.tool_name != spec.name
        ):
            return PolicyDecision(False, "approval_binding_mismatch", "Approval mismatch")

        if approval.status not in {
            ApprovalStatus.APPROVED.value,
            ApprovalStatus.EXECUTING.value,
        }:
            return PolicyDecision(False, "approval_required", "No valid approval")

        if compute_payload_hash(approval.payload) != approval.payload_hash:
            return PolicyDecision(
                False, "approval_payload_tampered", "Approved payload was modified"
            )

        payload = approval.payload
        if (
            payload.get("tool") != spec.name
            or payload.get("workspace_id") != str(run.workspace_id)
            or payload.get("run_id") != str(run.id)
            or payload.get("step_id") != str(step.id)
        ):
            return PolicyDecision(False, "approval_binding_mismatch", "Payload mismatch")

        return ALLOW
