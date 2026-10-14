import re
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace_role import WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace
from app.repositories.workspace import (
    create_workspace,
    get_workspace_by_id,
    get_workspace_by_slug,
    list_workspaces_for_user,
    update_workspace,
)
from app.repositories.workspace_membership import (
    create_membership,
    get_membership,
)
from app.schemas.workspace import WorkspaceCreate, WorkspaceUpdate
from app.services.audit import record_audit_event


def slugify_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    short_suffix = uuid4().hex[:6]
    return f"{cleaned or 'workspace'}-{short_suffix}"


async def create_personal_workspace_for_user(
    session: AsyncSession,
    *,
    user: User,
) -> Workspace:
    """Create a default Personal Workspace for a user if they do not already have one."""
    slug = f"personal-{user.id}"
    existing = await get_workspace_by_slug(session, slug)
    if existing is not None:
        return existing

    name = f"{user.full_name or 'Personal'}'s Workspace"
    workspace = await create_workspace(
        session,
        name=name,
        slug=slug,
        created_by=user.id,
        description="Personal workspace",
    )

    await create_membership(
        session,
        workspace_id=workspace.id,
        user_id=user.id,
        role=WorkspaceRole.OWNER,
    )

    await record_audit_event(
        session,
        workspace_id=workspace.id,
        action="workspace.create",
        resource_type="workspace",
        actor_id=user.id,
        resource_id=workspace.id,
        details={"type": "personal", "name": workspace.name},
    )

    return workspace


async def create_user_workspace(
    session: AsyncSession,
    *,
    user: User,
    data: WorkspaceCreate,
) -> tuple[Workspace, str]:
    """Create a new custom workspace and assign the creator as OWNER."""
    slug = slugify_name(data.name)

    workspace = await create_workspace(
        session,
        name=data.name.strip(),
        slug=slug,
        created_by=user.id,
        description=data.description.strip() if data.description else None,
    )

    await create_membership(
        session,
        workspace_id=workspace.id,
        user_id=user.id,
        role=WorkspaceRole.OWNER,
    )

    await record_audit_event(
        session,
        workspace_id=workspace.id,
        action="workspace.create",
        resource_type="workspace",
        actor_id=user.id,
        resource_id=workspace.id,
        details={"name": workspace.name},
    )

    return workspace, WorkspaceRole.OWNER.value


async def list_user_workspaces(
    session: AsyncSession,
    *,
    user: User,
) -> list[tuple[Workspace, str]]:
    """List all active workspaces for user along with their membership role."""
    return await list_workspaces_for_user(session, user.id)


async def get_workspace_for_user(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
) -> tuple[Workspace, str] | None:
    """Get a workspace only if the user is a valid member."""
    membership = await get_membership(
        session,
        workspace_id=workspace_id,
        user_id=user.id,
    )
    if membership is None:
        return None

    workspace = await get_workspace_by_id(session, workspace_id)
    if workspace is None:
        return None

    return workspace, membership.role


async def update_user_workspace(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
    data: WorkspaceUpdate,
) -> Workspace | None:
    """Update workspace details (requires workspace.update permission, checked at API layer)."""
    workspace = await get_workspace_by_id(session, workspace_id)
    if workspace is None:
        return None

    updated = await update_workspace(
        session,
        workspace=workspace,
        name=data.name.strip() if data.name else None,
        description=data.description.strip() if data.description is not None else None,
    )

    await record_audit_event(
        session,
        workspace_id=workspace.id,
        action="workspace.update",
        resource_type="workspace",
        actor_id=user.id,
        resource_id=workspace.id,
        details={"name": updated.name},
    )

    return updated
