from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace_role import AuditOutcome
from app.models.security_audit_event import SecurityAuditEvent
from app.models.user import User


async def create_audit_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    action: str,
    resource_type: str,
    actor_id: UUID | None = None,
    resource_id: UUID | None = None,
    outcome: str | AuditOutcome = AuditOutcome.SUCCESS,
    details: dict[str, Any] | None = None,
) -> SecurityAuditEvent:
    outcome_value = outcome.value if isinstance(outcome, AuditOutcome) else str(outcome)
    event = SecurityAuditEvent(
        workspace_id=workspace_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome_value,
        details=details,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def list_audit_events_for_workspace(
    session: AsyncSession,
    workspace_id: UUID,
    *,
    action: str | None = None,
    actor_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[tuple[SecurityAuditEvent, User | None]]:
    query = (
        select(SecurityAuditEvent, User)
        .outerjoin(User, User.id == SecurityAuditEvent.actor_id)
        .where(SecurityAuditEvent.workspace_id == workspace_id)
    )

    if action:
        query = query.where(SecurityAuditEvent.action == action)
    if actor_id:
        query = query.where(SecurityAuditEvent.actor_id == actor_id)

    query = query.order_by(SecurityAuditEvent.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    return [(row[0], row[1]) for row in result.all()]


async def count_audit_events_for_workspace(
    session: AsyncSession,
    workspace_id: UUID,
    *,
    action: str | None = None,
    actor_id: UUID | None = None,
) -> int:
    query = select(func.count(SecurityAuditEvent.id)).where(
        SecurityAuditEvent.workspace_id == workspace_id
    )

    if action:
        query = query.where(SecurityAuditEvent.action == action)
    if actor_id:
        query = query.where(SecurityAuditEvent.actor_id == actor_id)

    result = await session.execute(query)
    return result.scalar_one()
