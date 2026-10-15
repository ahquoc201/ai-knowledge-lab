from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace_role import WorkspaceRole
from app.models.user import User
from app.models.workspace_membership import WorkspaceMembership


async def create_membership(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    role: str | WorkspaceRole,
) -> WorkspaceMembership:
    role_value = role.value if isinstance(role, WorkspaceRole) else str(role)
    membership = WorkspaceMembership(
        workspace_id=workspace_id,
        user_id=user_id,
        role=role_value,
    )
    session.add(membership)
    await session.commit()
    await session.refresh(membership)
    return membership


async def get_membership(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> WorkspaceMembership | None:
    result = await session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_memberships_for_workspace(
    session: AsyncSession,
    workspace_id: UUID,
) -> list[tuple[WorkspaceMembership, User]]:
    """List all members of a workspace along with user profile information."""
    result = await session.execute(
        select(WorkspaceMembership, User)
        .join(User, User.id == WorkspaceMembership.user_id)
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .order_by(WorkspaceMembership.created_at.asc())
    )
    return [(row[0], row[1]) for row in result.all()]


async def count_owners_for_workspace(
    session: AsyncSession,
    workspace_id: UUID,
) -> int:
    result = await session.execute(
        select(func.count(WorkspaceMembership.id)).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role == WorkspaceRole.OWNER.value,
        )
    )
    return result.scalar_one()


async def update_member_role(
    session: AsyncSession,
    *,
    membership: WorkspaceMembership,
    role: str | WorkspaceRole,
) -> WorkspaceMembership:
    role_value = role.value if isinstance(role, WorkspaceRole) else str(role)
    membership.role = role_value
    membership.updated_at = func.now()

    await session.commit()
    await session.refresh(membership)
    return membership


async def delete_membership(
    session: AsyncSession,
    *,
    membership: WorkspaceMembership,
) -> None:
    await session.delete(membership)
    await session.commit()
