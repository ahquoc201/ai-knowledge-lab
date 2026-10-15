from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace_role import InvitationStatus, WorkspaceRole
from app.models.workspace_invitation import WorkspaceInvitation


async def create_invitation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    invited_by: UUID,
    email: str,
    role: str | WorkspaceRole,
    token_hash: str,
    expires_at: datetime,
) -> WorkspaceInvitation:
    role_value = role.value if isinstance(role, WorkspaceRole) else str(role)
    invitation = WorkspaceInvitation(
        workspace_id=workspace_id,
        invited_by=invited_by,
        email=email.strip().lower(),
        role=role_value,
        token_hash=token_hash,
        status=InvitationStatus.PENDING.value,
        expires_at=expires_at,
    )
    session.add(invitation)
    await session.commit()
    await session.refresh(invitation)
    return invitation


async def get_invitation_by_token_hash(
    session: AsyncSession,
    token_hash: str,
) -> WorkspaceInvitation | None:
    result = await session.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.token_hash == token_hash
        )
    )
    return result.scalar_one_or_none()


async def get_invitation_by_id(
    session: AsyncSession,
    invitation_id: UUID,
) -> WorkspaceInvitation | None:
    result = await session.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.id == invitation_id
        )
    )
    return result.scalar_one_or_none()


async def get_active_invitation_for_email(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    email: str,
) -> WorkspaceInvitation | None:
    normalized_email = email.strip().lower()
    result = await session.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.email == normalized_email,
            WorkspaceInvitation.status == InvitationStatus.PENDING.value,
            WorkspaceInvitation.expires_at > func.now(),
        )
    )
    return result.scalar_one_or_none()


async def list_invitations_for_workspace(
    session: AsyncSession,
    workspace_id: UUID,
) -> list[WorkspaceInvitation]:
    result = await session.execute(
        select(WorkspaceInvitation)
        .where(WorkspaceInvitation.workspace_id == workspace_id)
        .order_by(WorkspaceInvitation.created_at.desc())
    )
    return list(result.scalars().all())


async def update_invitation_status(
    session: AsyncSession,
    *,
    invitation: WorkspaceInvitation,
    status: str | InvitationStatus,
) -> WorkspaceInvitation:
    status_value = status.value if isinstance(status, InvitationStatus) else str(status)
    invitation.status = status_value
    invitation.updated_at = func.now()

    await session.commit()
    await session.refresh(invitation)
    return invitation
