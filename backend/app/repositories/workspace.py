from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace_role import WorkspaceStatus
from app.models.workspace import Workspace
from app.models.workspace_membership import WorkspaceMembership


async def create_workspace(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    created_by: UUID | None,
    description: str | None = None,
) -> Workspace:
    workspace = Workspace(
        name=name,
        slug=slug,
        description=description,
        status=WorkspaceStatus.ACTIVE.value,
        created_by=created_by,
    )
    session.add(workspace)
    await session.commit()
    await session.refresh(workspace)
    return workspace


async def get_workspace_by_id(
    session: AsyncSession,
    workspace_id: UUID,
) -> Workspace | None:
    result = await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    return result.scalar_one_or_none()


async def get_workspace_by_slug(
    session: AsyncSession,
    slug: str,
) -> Workspace | None:
    result = await session.execute(
        select(Workspace).where(Workspace.slug == slug)
    )
    return result.scalar_one_or_none()


async def list_workspaces_for_user(
    session: AsyncSession,
    user_id: UUID,
) -> list[tuple[Workspace, str]]:
    """List all active workspaces the user belongs to along with their role."""
    result = await session.execute(
        select(Workspace, WorkspaceMembership.role)
        .join(
            WorkspaceMembership,
            WorkspaceMembership.workspace_id == Workspace.id,
        )
        .where(
            WorkspaceMembership.user_id == user_id,
            Workspace.status == WorkspaceStatus.ACTIVE.value,
        )
        .order_by(Workspace.created_at.asc())
    )
    return [(row[0], row[1]) for row in result.all()]


async def update_workspace(
    session: AsyncSession,
    *,
    workspace: Workspace,
    name: str | None = None,
    description: str | None = None,
) -> Workspace:
    if name is not None:
        workspace.name = name
    if description is not None:
        workspace.description = description
    workspace.updated_at = func.now()

    await session.commit()
    await session.refresh(workspace)
    return workspace


async def delete_workspace(
    session: AsyncSession,
    *,
    workspace: Workspace,
) -> None:
    await session.delete(workspace)
    await session.commit()


async def resolve_or_create_user_workspace_id(
    session: AsyncSession,
    user_id: UUID,
) -> UUID:
    """Find the user's default workspace or auto-create a personal workspace."""
    result = await session.execute(
        select(WorkspaceMembership.workspace_id)
        .where(WorkspaceMembership.user_id == user_id)
        .order_by(WorkspaceMembership.created_at.asc())
        .limit(1)
    )
    ws_id = result.scalar_one_or_none()
    if ws_id is not None:
        return ws_id

    from app.core.workspace_role import WorkspaceRole

    ws = Workspace(
        name="Personal Workspace",
        slug=f"personal-{user_id}",
        status=WorkspaceStatus.ACTIVE.value,
        created_by=user_id,
    )
    session.add(ws)
    await session.flush()

    mem = WorkspaceMembership(
        workspace_id=ws.id,
        user_id=user_id,
        role=WorkspaceRole.OWNER.value,
    )
    session.add(mem)
    await session.flush()

    return ws.id
