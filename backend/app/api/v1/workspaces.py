from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_workspace_membership,
    require_permission,
)
from app.core.workspace_role import WorkspacePermission
from app.db.session import get_session
from app.models.user import User
from app.models.workspace_membership import WorkspaceMembership
from app.repositories.security_audit_event import (
    count_audit_events_for_workspace,
    list_audit_events_for_workspace,
)
from app.schemas.workspace import (
    SecurityAuditEventResponse,
    SecurityAuditListResponse,
    WorkspaceCreate,
    WorkspaceInviteRequest,
    WorkspaceInviteResponse,
    WorkspaceMemberResponse,
    WorkspaceMemberRoleUpdate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services.membership import (
    AlreadyMemberError,
    CannotManageRoleError,
    InvalidInvitationError,
    LastOwnerProtectionError,
    accept_invitation,
    change_member_role,
    invite_member,
    leave_workspace,
    list_workspace_members,
    remove_member,
)
from app.services.workspace import (
    create_user_workspace,
    get_workspace_for_user,
    list_user_workspaces,
    update_user_workspace,
)

router = APIRouter(
    prefix="/workspaces",
    tags=["Workspaces"],
)


class AcceptInvitationRequest(BaseModel):
    token: str


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace_endpoint(
    data: WorkspaceCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkspaceResponse:
    workspace, role = await create_user_workspace(
        session,
        user=current_user,
        data=data,
    )
    res = WorkspaceResponse.model_validate(workspace)
    res.current_user_role = role
    return res


@router.get(
    "",
    response_model=list[WorkspaceResponse],
)
async def list_workspaces_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[WorkspaceResponse]:
    workspaces = await list_user_workspaces(
        session,
        user=current_user,
    )
    result: list[WorkspaceResponse] = []
    for ws, role in workspaces:
        item = WorkspaceResponse.model_validate(ws)
        item.current_user_role = role
        result.append(item)
    return result


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
)
async def get_workspace_endpoint(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _membership: Annotated[
        WorkspaceMembership,
        Depends(require_permission(WorkspacePermission.WORKSPACE_READ)),
    ],
) -> WorkspaceResponse:
    found = await get_workspace_for_user(
        session,
        user=current_user,
        workspace_id=workspace_id,
    )
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    ws, role = found
    res = WorkspaceResponse.model_validate(ws)
    res.current_user_role = role
    return res


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
)
async def update_workspace_endpoint(
    workspace_id: UUID,
    data: WorkspaceUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_permission(WorkspacePermission.WORKSPACE_UPDATE)),
    ],
) -> WorkspaceResponse:
    updated = await update_user_workspace(
        session,
        user=current_user,
        workspace_id=workspace_id,
        data=data,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    res = WorkspaceResponse.model_validate(updated)
    res.current_user_role = membership.role
    return res


@router.get(
    "/{workspace_id}/members",
    response_model=list[WorkspaceMemberResponse],
)
async def list_members_endpoint(
    workspace_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _membership: Annotated[
        WorkspaceMembership,
        Depends(require_permission(WorkspacePermission.MEMBER_LIST)),
    ],
) -> list[WorkspaceMemberResponse]:
    members = await list_workspace_members(
        session,
        workspace_id=workspace_id,
    )
    return [
        WorkspaceMemberResponse(
            id=m.id,
            user_id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=m.role,
            created_at=m.created_at,
        )
        for m, u in members
    ]


@router.post(
    "/{workspace_id}/invitations",
    response_model=WorkspaceInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member_endpoint(
    workspace_id: UUID,
    data: WorkspaceInviteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_permission(WorkspacePermission.MEMBER_INVITE)),
    ],
) -> WorkspaceInviteResponse:
    try:
        invitation, token = await invite_member(
            session,
            actor=current_user,
            actor_role=membership.role,
            workspace_id=workspace_id,
            data=data,
        )
    except AlreadyMemberError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except CannotManageRoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    res = WorkspaceInviteResponse.model_validate(invitation)
    res.invitation_token = token
    return res


@router.post(
    "/invitations/accept",
    response_model=WorkspaceMemberResponse,
)
async def accept_invitation_endpoint(
    data: AcceptInvitationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkspaceMemberResponse:
    try:
        membership = await accept_invitation(
            session,
            user=current_user,
            token=data.token,
        )
    except (InvalidInvitationError, AlreadyMemberError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return WorkspaceMemberResponse(
        id=membership.id,
        user_id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.patch(
    "/{workspace_id}/members/{target_user_id}",
    response_model=WorkspaceMemberResponse,
)
async def change_member_role_endpoint(
    workspace_id: UUID,
    target_user_id: UUID,
    data: WorkspaceMemberRoleUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_permission(WorkspacePermission.MEMBER_ROLE_CHANGE)),
    ],
) -> WorkspaceMemberResponse:
    try:
        updated = await change_member_role(
            session,
            actor=current_user,
            actor_role=membership.role,
            workspace_id=workspace_id,
            target_user_id=target_user_id,
            new_role=data.role,
        )
    except CannotManageRoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LastOwnerProtectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    from app.repositories.user import get_user_by_id

    target_user = await get_user_by_id(session, target_user_id)

    return WorkspaceMemberResponse(
        id=updated.id,
        user_id=target_user_id,
        email=target_user.email if target_user else "",
        full_name=target_user.full_name if target_user else None,
        role=updated.role,
        created_at=updated.created_at,
    )


@router.delete(
    "/{workspace_id}/members/{target_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member_endpoint(
    workspace_id: UUID,
    target_user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_permission(WorkspacePermission.MEMBER_REMOVE)),
    ],
) -> None:
    try:
        await remove_member(
            session,
            actor=current_user,
            actor_role=membership.role,
            workspace_id=workspace_id,
            target_user_id=target_user_id,
        )
    except CannotManageRoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LastOwnerProtectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{workspace_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def leave_workspace_endpoint(
    workspace_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _membership: Annotated[
        WorkspaceMembership,
        Depends(get_workspace_membership),
    ],
) -> None:
    try:
        await leave_workspace(
            session,
            user=current_user,
            workspace_id=workspace_id,
        )
    except LastOwnerProtectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/{workspace_id}/audit-events",
    response_model=SecurityAuditListResponse,
)
async def list_audit_events_endpoint(
    workspace_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _membership: Annotated[
        WorkspaceMembership,
        Depends(require_permission(WorkspacePermission.AUDIT_READ)),
    ],
    action: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SecurityAuditListResponse:
    events = await list_audit_events_for_workspace(
        session,
        workspace_id=workspace_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    total = await count_audit_events_for_workspace(
        session,
        workspace_id=workspace_id,
        action=action,
    )
    return SecurityAuditListResponse(
        items=[
            SecurityAuditEventResponse(
                id=ev.id,
                workspace_id=ev.workspace_id,
                actor_id=ev.actor_id,
                actor_email=user.email if user else None,
                action=ev.action,
                resource_type=ev.resource_type,
                resource_id=ev.resource_id,
                outcome=ev.outcome,
                details=ev.details,
                created_at=ev.created_at,
            )
            for ev, user in events
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
