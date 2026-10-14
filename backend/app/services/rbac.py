from app.core.workspace_role import WorkspacePermission, WorkspaceRole

ROLE_PERMISSIONS: dict[WorkspaceRole, set[WorkspacePermission]] = {
    WorkspaceRole.OWNER: {
        WorkspacePermission.WORKSPACE_READ,
        WorkspacePermission.WORKSPACE_UPDATE,
        WorkspacePermission.WORKSPACE_DELETE,
        WorkspacePermission.MEMBER_LIST,
        WorkspacePermission.MEMBER_INVITE,
        WorkspacePermission.MEMBER_ROLE_CHANGE,
        WorkspacePermission.MEMBER_REMOVE,
        WorkspacePermission.DOCUMENT_READ,
        WorkspacePermission.DOCUMENT_CREATE,
        WorkspacePermission.DOCUMENT_UPDATE,
        WorkspacePermission.DOCUMENT_DELETE,
        WorkspacePermission.DOCUMENT_REPROCESS,
        WorkspacePermission.CHAT_READ,
        WorkspacePermission.CHAT_CREATE,
        WorkspacePermission.AUDIT_READ,
    },
    WorkspaceRole.ADMIN: {
        WorkspacePermission.WORKSPACE_READ,
        WorkspacePermission.WORKSPACE_UPDATE,
        WorkspacePermission.MEMBER_LIST,
        WorkspacePermission.MEMBER_INVITE,
        WorkspacePermission.MEMBER_REMOVE,
        WorkspacePermission.DOCUMENT_READ,
        WorkspacePermission.DOCUMENT_CREATE,
        WorkspacePermission.DOCUMENT_UPDATE,
        WorkspacePermission.DOCUMENT_DELETE,
        WorkspacePermission.DOCUMENT_REPROCESS,
        WorkspacePermission.CHAT_READ,
        WorkspacePermission.CHAT_CREATE,
        WorkspacePermission.AUDIT_READ,
    },
    WorkspaceRole.EDITOR: {
        WorkspacePermission.WORKSPACE_READ,
        WorkspacePermission.MEMBER_LIST,
        WorkspacePermission.DOCUMENT_READ,
        WorkspacePermission.DOCUMENT_CREATE,
        WorkspacePermission.DOCUMENT_UPDATE,
        WorkspacePermission.DOCUMENT_DELETE,
        WorkspacePermission.DOCUMENT_REPROCESS,
        WorkspacePermission.CHAT_READ,
        WorkspacePermission.CHAT_CREATE,
    },
    WorkspaceRole.VIEWER: {
        WorkspacePermission.WORKSPACE_READ,
        WorkspacePermission.MEMBER_LIST,
        WorkspacePermission.DOCUMENT_READ,
        WorkspacePermission.CHAT_READ,
        WorkspacePermission.CHAT_CREATE,
    },
}


def has_permission(role: str | WorkspaceRole, permission: WorkspacePermission) -> bool:
    """Check if a given role has the specified permission."""
    try:
        ws_role = WorkspaceRole(role)
    except ValueError:
        return False

    return permission in ROLE_PERMISSIONS.get(ws_role, set())


def can_manage_target_role(actor_role: str | WorkspaceRole, target_role: str | WorkspaceRole) -> bool:
    """Check if an actor role is allowed to modify/remove a member with target_role.

    Rules:
    - OWNER can manage anyone.
    - ADMIN can manage EDITOR and VIEWER, but cannot manage OWNER or other ADMINs.
    - EDITOR and VIEWER cannot manage anyone.
    """
    try:
        actor = WorkspaceRole(actor_role)
        target = WorkspaceRole(target_role)
    except ValueError:
        return False

    if actor == WorkspaceRole.OWNER:
        return True

    if actor == WorkspaceRole.ADMIN:
        return target in {WorkspaceRole.EDITOR, WorkspaceRole.VIEWER}

    return False
