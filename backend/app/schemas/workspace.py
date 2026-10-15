from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.workspace_role import WorkspaceRole


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str | None
    status: str
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    current_user_role: str | None = None

    model_config = ConfigDict(from_attributes=True)


class WorkspaceMemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    full_name: str | None
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceInviteRequest(BaseModel):
    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.VIEWER


class WorkspaceInviteResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    invitation_token: str | None = None

    model_config = ConfigDict(from_attributes=True)


class WorkspaceMemberRoleUpdate(BaseModel):
    role: WorkspaceRole


class SecurityAuditEventResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    actor_id: UUID | None
    actor_email: str | None = None
    action: str
    resource_type: str
    resource_id: UUID | None
    outcome: str
    details: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SecurityAuditListResponse(BaseModel):
    items: list[SecurityAuditEventResponse]
    total: int
    limit: int
    offset: int
