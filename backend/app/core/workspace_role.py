from enum import StrEnum


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    ERROR = "error"


class WorkspacePermission(StrEnum):
    # Workspace management
    WORKSPACE_READ = "workspace.read"
    WORKSPACE_UPDATE = "workspace.update"
    WORKSPACE_DELETE = "workspace.delete"

    # Membership management
    MEMBER_LIST = "member.list"
    MEMBER_INVITE = "member.invite"
    MEMBER_ROLE_CHANGE = "member.role_change"
    MEMBER_REMOVE = "member.remove"

    # Document operations
    DOCUMENT_READ = "document.read"
    DOCUMENT_CREATE = "document.create"
    DOCUMENT_UPDATE = "document.update"
    DOCUMENT_DELETE = "document.delete"
    DOCUMENT_REPROCESS = "document.reprocess"

    # Chat operations
    CHAT_READ = "chat.read"
    CHAT_CREATE = "chat.create"

    # Audit operations
    AUDIT_READ = "audit.read"
