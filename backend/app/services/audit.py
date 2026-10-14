import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace_role import AuditOutcome
from app.models.security_audit_event import SecurityAuditEvent
from app.repositories.security_audit_event import (
    create_audit_event,
)

logger = logging.getLogger(__name__)


async def record_audit_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    action: str,
    resource_type: str,
    actor_id: UUID | None = None,
    resource_id: UUID | None = None,
    outcome: str | AuditOutcome = AuditOutcome.SUCCESS,
    details: dict[str, Any] | None = None,
) -> SecurityAuditEvent | None:
    """Record an immutable security audit event without exposing secrets."""
    # Sanitize details: never persist password, tokens, or raw confidential keys
    sanitized_details = None
    if details:
        sensitive_keys = {"password", "token", "secret", "jwt", "access_token"}
        sanitized_details = {
            k: ("[REDACTED]" if any(s in k.lower() for s in sensitive_keys) else v)
            for k, v in details.items()
        }

    try:
        return await create_audit_event(
            session,
            workspace_id=workspace_id,
            action=action,
            resource_type=resource_type,
            actor_id=actor_id,
            resource_id=resource_id,
            outcome=outcome,
            details=sanitized_details,
        )
    except Exception:
        logger.exception("Failed to record security audit event for action: %s", action)
        return None
