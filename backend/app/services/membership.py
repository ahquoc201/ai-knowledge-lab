import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace_role import (
    AuditOutcome,
    InvitationStatus,
    WorkspaceRole,
)
from app.models.user import User
from app.models.workspace_invitation import WorkspaceInvitation
from app.models.workspace_membership import WorkspaceMembership
from app.repositories.user import get_user_by_email
from app.repositories.workspace_invitation import (
    create_invitation,
    get_active_invitation_for_email,
    get_invitation_by_token_hash,
    update_invitation_status,
)
from app.repositories.workspace_membership import (
    count_owners_for_workspace,
    create_membership,
    delete_membership,
    get_membership,
    list_memberships_for_workspace,
    update_member_role,
)
from app.schemas.workspace import WorkspaceInviteRequest
from app.services.audit import record_audit_event
from app.services.rbac import can_manage_target_role


class AlreadyMemberError(ValueError):
    """Raised when a user is already a member of the workspace."""


class CannotManageRoleError(PermissionError):
    """Raised when an actor attempts to manage a role beyond their privilege."""


class LastOwnerProtectionError(ValueError):
    """Raised when an operation would leave a workspace without an OWNER."""


class InvalidInvitationError(ValueError):
    """Raised when an invitation token is invalid, expired, or claimed by wrong user."""


async def list_workspace_members(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> list[tuple[WorkspaceMembership, User]]:
    return await list_memberships_for_workspace(session, workspace_id)


async def invite_member(
    session: AsyncSession,
    *,
    actor: User,
    actor_role: str,
    workspace_id: UUID,
    data: WorkspaceInviteRequest,
) -> tuple[WorkspaceInvitation, str]:
    target_email = data.email.strip().lower()

    # Rule 1: Cannot invite as OWNER (Owner must be promoted by existing Owner)
    if data.role == WorkspaceRole.OWNER:
        raise CannotManageRoleError("Cannot invite a member directly as OWNER")

    # Rule 2: ADMIN cannot invite as ADMIN (only Owner can invite Admin)
    if actor_role == WorkspaceRole.ADMIN.value and data.role != WorkspaceRole.VIEWER and data.role != WorkspaceRole.EDITOR:
        raise CannotManageRoleError("ADMINs can only invite members as EDITOR or VIEWER")

    # Rule 3: Check if target email already has an active membership
    existing_user = await get_user_by_email(session, target_email)
    if existing_user is not None:
        existing_membership = await get_membership(
            session,
            workspace_id=workspace_id,
            user_id=existing_user.id,
        )
        if existing_membership is not None:
            raise AlreadyMemberError("User is already a member of this workspace")

    # Rule 4: If an active invitation already exists for this email, expire it
    existing_invitation = await get_active_invitation_for_email(
        session,
        workspace_id=workspace_id,
        email=target_email,
    )
    if existing_invitation is not None:
        await update_invitation_status(
            session,
            invitation=existing_invitation,
            status=InvitationStatus.EXPIRED,
        )

    # Generate single-use secure random token and store its sha256 hash
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(days=7)

    invitation = await create_invitation(
        session,
        workspace_id=workspace_id,
        invited_by=actor.id,
        email=target_email,
        role=data.role,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    await record_audit_event(
        session,
        workspace_id=workspace_id,
        action="member.invite",
        resource_type="invitation",
        actor_id=actor.id,
        resource_id=invitation.id,
        details={"email": target_email, "role": data.role.value},
    )

    return invitation, raw_token


async def accept_invitation(
    session: AsyncSession,
    *,
    user: User,
    token: str,
) -> WorkspaceMembership:
    token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    invitation = await get_invitation_by_token_hash(session, token_hash)

    if invitation is None:
        raise InvalidInvitationError("Invalid invitation token")

    if invitation.status != InvitationStatus.PENDING.value:
        raise InvalidInvitationError("Invitation is no longer pending")

    if invitation.expires_at < datetime.now(UTC):
        await update_invitation_status(
            session,
            invitation=invitation,
            status=InvitationStatus.EXPIRED,
        )
        raise InvalidInvitationError("Invitation has expired")

    # Verify recipient email matches the invitation email
    if invitation.email.lower() != user.email.lower():
        await record_audit_event(
            session,
            workspace_id=invitation.workspace_id,
            action="member.accept_invitation",
            resource_type="invitation",
            actor_id=user.id,
            resource_id=invitation.id,
            outcome=AuditOutcome.DENIED,
            details={"reason": "email_mismatch"},
        )
        raise InvalidInvitationError(
            f"This invitation was sent to {invitation.email}, but you are logged in as {user.email}"
        )

    # Verify user is not already a member
    existing_membership = await get_membership(
        session,
        workspace_id=invitation.workspace_id,
        user_id=user.id,
    )
    if existing_membership is not None:
        await update_invitation_status(
            session,
            invitation=invitation,
            status=InvitationStatus.ACCEPTED,
        )
        raise AlreadyMemberError("You are already a member of this workspace")

    membership = await create_membership(
        session,
        workspace_id=invitation.workspace_id,
        user_id=user.id,
        role=invitation.role,
    )

    await update_invitation_status(
        session,
        invitation=invitation,
        status=InvitationStatus.ACCEPTED,
    )

    await record_audit_event(
        session,
        workspace_id=invitation.workspace_id,
        action="member.accept_invitation",
        resource_type="membership",
        actor_id=user.id,
        resource_id=membership.id,
        details={"role": invitation.role},
    )

    return membership


async def change_member_role(
    session: AsyncSession,
    *,
    actor: User,
    actor_role: str,
    workspace_id: UUID,
    target_user_id: UUID,
    new_role: WorkspaceRole,
) -> WorkspaceMembership:
    if actor.id == target_user_id:
        target_membership = await get_membership(
            session,
            workspace_id=workspace_id,
            user_id=target_user_id,
        )
        if target_membership and target_membership.role == WorkspaceRole.OWNER.value and new_role != WorkspaceRole.OWNER:
            owner_count = await count_owners_for_workspace(session, workspace_id)
            if owner_count <= 1:
                raise LastOwnerProtectionError("Cannot demote the last owner (only owner) of the workspace")
        raise CannotManageRoleError("You cannot change your own role")

    target_membership = await get_membership(
        session,
        workspace_id=workspace_id,
        user_id=target_user_id,
    )
    if target_membership is None:
        raise ValueError("Member not found in workspace")

    # Validate privilege: can actor manage target's current role?
    if not can_manage_target_role(actor_role, target_membership.role):
        raise CannotManageRoleError("You do not have permission to modify this member's role")

    # Validate privilege: can actor assign new_role?
    if not can_manage_target_role(actor_role, new_role):
        raise CannotManageRoleError("You do not have permission to grant this role")

    # Protection: if target was OWNER and is downgraded, check last owner rule
    if target_membership.role == WorkspaceRole.OWNER.value and new_role != WorkspaceRole.OWNER:
        owner_count = await count_owners_for_workspace(session, workspace_id)
        if owner_count <= 1:
            raise LastOwnerProtectionError("Cannot downgrade the last owner of the workspace")

    updated = await update_member_role(
        session,
        membership=target_membership,
        role=new_role,
    )

    await record_audit_event(
        session,
        workspace_id=workspace_id,
        action="member.role_change",
        resource_type="membership",
        actor_id=actor.id,
        resource_id=target_membership.id,
        details={
            "target_user_id": str(target_user_id),
            "old_role": target_membership.role,
            "new_role": new_role.value,
        },
    )

    return updated


async def remove_member(
    session: AsyncSession,
    *,
    actor: User,
    actor_role: str,
    workspace_id: UUID,
    target_user_id: UUID,
) -> None:
    if actor.id == target_user_id:
        # If removing self, redirect to leave_workspace
        await leave_workspace(session, user=actor, workspace_id=workspace_id)
        return

    target_membership = await get_membership(
        session,
        workspace_id=workspace_id,
        user_id=target_user_id,
    )
    if target_membership is None:
        raise ValueError("Member not found in workspace")

    if not can_manage_target_role(actor_role, target_membership.role):
        raise CannotManageRoleError("You do not have permission to remove this member")

    if target_membership.role == WorkspaceRole.OWNER.value:
        owner_count = await count_owners_for_workspace(session, workspace_id)
        if owner_count <= 1:
            raise LastOwnerProtectionError("Cannot remove the last owner (only owner) of the workspace")

    await delete_membership(session, membership=target_membership)

    await record_audit_event(
        session,
        workspace_id=workspace_id,
        action="member.remove",
        resource_type="membership",
        actor_id=actor.id,
        resource_id=target_membership.id,
        details={"removed_user_id": str(target_user_id)},
    )


async def leave_workspace(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
) -> None:
    membership = await get_membership(
        session,
        workspace_id=workspace_id,
        user_id=user.id,
    )
    if membership is None:
        raise ValueError("You are not a member of this workspace")

    if membership.role == WorkspaceRole.OWNER.value:
        owner_count = await count_owners_for_workspace(session, workspace_id)
        if owner_count <= 1:
            raise LastOwnerProtectionError(
                "Cannot remove or leave as the last owner (only owner) of the workspace"
            )

    await delete_membership(session, membership=membership)

    await record_audit_event(
        session,
        workspace_id=workspace_id,
        action="member.leave",
        resource_type="membership",
        actor_id=user.id,
        resource_id=membership.id,
    )
