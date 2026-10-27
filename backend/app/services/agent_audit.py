"""Security audit helper for the agent runtime.

Audit rows must never carry document content, tool output or secrets. Details are
restricted to an allowlist of identifier-like keys with short scalar values, so
callers cannot accidentally persist sensitive payloads.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace_role import AuditOutcome
from app.services.audit import record_audit_event

ALLOWED_AUDIT_KEYS: frozenset[str] = frozenset(
    {
        "run_id",
        "step_id",
        "step_index",
        "approval_id",
        "tool",
        "side_effect",
        "reason_code",
        "error_code",
        "permission",
        "role",
        "status",
        "decision",
        "document_id",
        "result_count",
        "payload_hash",
        "decided_by",
        "initiated_by",
        "correlation_id",
    }
)

_MAX_VALUE_LENGTH = 100


def sanitize_audit_details(details: dict[str, Any] | None) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in (details or {}).items():
        if key not in ALLOWED_AUDIT_KEYS:
            continue
        if value is None or isinstance(value, bool | int | float):
            clean[key] = value
        elif isinstance(value, UUID):
            clean[key] = str(value)
        elif isinstance(value, str):
            clean[key] = value[:_MAX_VALUE_LENGTH]
    return clean


async def audit_agent_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    action: str,
    actor_id: UUID | None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    resource_type: str = "agent_run",
    resource_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    await record_audit_event(
        session,
        workspace_id=workspace_id,
        action=action,
        resource_type=resource_type,
        actor_id=actor_id,
        resource_id=resource_id,
        outcome=outcome,
        details=sanitize_audit_details(details),
    )
