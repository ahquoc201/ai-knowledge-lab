from collections.abc import Callable
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.workspace_role import WorkspacePermission
from app.db.session import get_session
from app.models.user import User
from app.models.workspace_membership import WorkspaceMembership
from app.repositories.user import get_user_by_id
from app.repositories.workspace_membership import get_membership
from app.services.rbac import has_permission

settings = get_settings()

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials,
        Depends(bearer_scheme),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        subject = payload.get("sub")

        if subject is None:
            raise credentials_exception

        user_id = UUID(subject)

    except (InvalidTokenError, ValueError) as exc:
        raise credentials_exception from exc

    user = await get_user_by_id(session, user_id)

    if user is None or not user.is_active:
        raise credentials_exception

    return user


async def get_workspace_membership(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    workspace_id: UUID | None = None,
    x_workspace_id: Annotated[UUID | None, Header(alias="X-Workspace-Id")] = None,
) -> WorkspaceMembership:
    """Validate that the authenticated user is an active member of the requested workspace."""
    target_workspace_id = workspace_id or x_workspace_id

    if target_workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace ID is required in URL path or X-Workspace-Id header",
        )

    membership = await get_membership(
        session,
        workspace_id=target_workspace_id,
        user_id=current_user.id,
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace",
        )

    return membership


def require_permission(
    permission: WorkspacePermission,
) -> Callable[..., WorkspaceMembership]:
    """Dependency factory that validates the caller has the required workspace permission."""

    async def permission_checker(
        membership: Annotated[
            WorkspaceMembership,
            Depends(get_workspace_membership),
        ],
    ) -> WorkspaceMembership:
        if not has_permission(membership.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires {permission.value}",
            )
        return membership

    return permission_checker