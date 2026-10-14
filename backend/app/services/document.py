
import logging
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.document_status import DocumentStatus
from app.models.document import Document
from app.models.user import User
from app.repositories.document import (
    claim_file_document_reprocessing,
    claim_workspace_file_reprocessing,
    count_documents_by_user,
    count_documents_by_workspace,
    create_document,
    delete_document,
    get_document_by_id_and_workspace,
    get_document_by_id_and_workspace_for_update,
    get_document_by_id_for_user,
    get_document_by_id_for_user_for_update,
    list_documents_by_user,
    list_documents_by_workspace,
    recover_stale_file_processing,
    recover_workspace_stale_file_processing,
    save_document,
    update_document_content,
    update_document_status,
)
from app.schemas.document import DocumentCreate, DocumentUpdate
from app.services.file_storage import (
    InvalidStorageKeyError,
    delete_stored_file,
)

logger = logging.getLogger(__name__)


# ============================================================
# Exceptions
# ============================================================


class DocumentProcessingError(ValueError):
    """Document cannot be deleted while processing."""


class UnsupportedDocumentContentUpdateError(ValueError):
    """Content updates are not supported for file documents."""


class InvalidDocumentUpdateError(ValueError):
    """Invalid document update request."""


# ============================================================
# Create Document
# ============================================================


async def create_user_document(
    session: AsyncSession,
    *,
    user: User,
    data: DocumentCreate,
    storage_key: str | None = None,
    workspace_id: UUID | None = None,
) -> Document:
    return await create_document(
        session,
        user_id=user.id,
        workspace_id=workspace_id,
        title=data.title,
        content=data.content,
        source_type=data.source_type,
        source_name=data.source_name,
        mime_type=data.mime_type,
        storage_key=storage_key,
    )


# ============================================================
# List Documents
# ============================================================


async def list_user_documents(
    session: AsyncSession,
    *,
    user: User,
    search: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Document], int]:
    documents = await list_documents_by_user(
        session,
        user.id,
        search=search,
        status=status,
        source_type=source_type,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )

    total = await count_documents_by_user(
        session,
        user.id,
        search=search,
        status=status,
        source_type=source_type,
    )

    return documents, total


async def list_workspace_documents(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    search: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Document], int]:
    documents = await list_documents_by_workspace(
        session,
        workspace_id=workspace_id,
        search=search,
        status=status,
        source_type=source_type,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )

    total = await count_documents_by_workspace(
        session,
        workspace_id=workspace_id,
        search=search,
        status=status,
        source_type=source_type,
    )

    return documents, total


# ============================================================
# Get Document
# ============================================================


async def get_user_document(
    session: AsyncSession,
    *,
    user: User,
    document_id: UUID,
) -> Document | None:
    return await get_document_by_id_for_user(
        session,
        document_id=document_id,
        user_id=user.id,
    )


async def get_workspace_document(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    document_id: UUID,
) -> Document | None:
    return await get_document_by_id_and_workspace(
        session,
        document_id=document_id,
        workspace_id=workspace_id,
    )



# ============================================================
# Update Document Status / Content
# ============================================================


async def set_document_status(
    session: AsyncSession,
    *,
    document: Document,
    status: DocumentStatus,
    error_message: str | None = None,
) -> Document:
    return await update_document_status(
        session,
        document=document,
        status=status.value,
        error_message=error_message,
    )


async def set_document_content(
    session: AsyncSession,
    *,
    document: Document,
    content: str,
) -> Document:
    return await update_document_content(
        session,
        document=document,
        content=content,
    )


# ============================================================
# Delete Document with PostgreSQL Row Lock
# ============================================================


async def delete_user_document(
    session: AsyncSession,
    *,
    user: User,
    document_id: UUID,
    workspace_id: UUID | None = None,
) -> bool:
    """
    Delete a user-owned document safely.

    Rules:
    - Lock the document row before checking its status.
    - Reject deletion while the document is PROCESSING.
    - Delete the database record before the source file.
    - Preserve the source file if the DB deletion fails.
    - Log filesystem cleanup failures without masking
      a successfully committed database deletion.
    """

    document = await get_document_by_id_for_user_for_update(
        session,
        document_id=document_id,
        user_id=user.id,
    )

    if document is None:
        await session.rollback()
        return False

    if workspace_id is not None and getattr(document, "workspace_id", None) is not None and document.workspace_id != workspace_id:
        await session.rollback()
        return False

    if document.status == DocumentStatus.PROCESSING.value:
        # Use PostgreSQL time to avoid application clock skew.
        cutoff = await session.scalar(
            select(func.now() - text("INTERVAL '5 minutes'"))
        )

        heartbeat_at = document.processing_heartbeat_at
        started_at = document.processing_started_at

        lease_expired = (
            (
                heartbeat_at is not None
                and heartbeat_at < cutoff
            )
            or (
                heartbeat_at is None
                and (
                    started_at is None
                    or started_at < cutoff
                )
            )
        )

        if not lease_expired:
            await session.rollback()

            raise DocumentProcessingError(
                "Document is currently processing"
            )

        # Lease expired. Continue deleting while holding
        # the PostgreSQL row lock. Do not commit here.

    # Save the storage key before deleting the DB record.
    storage_key = document.storage_key

    # Delete and commit while holding the row lock.
    # The commit releases the PostgreSQL row lock.
    await delete_document(
        session,
        document=document,
    )

    # Only delete the original file after DB commit succeeds.
    if storage_key:
        try:
            delete_stored_file(storage_key)

        except (OSError, InvalidStorageKeyError):
            logger.exception(
                "Failed to clean up source file for document %s",
                document_id,
            )

    return True


# ============================================================
# Update Document
# ============================================================


async def update_user_document(
    session: AsyncSession,
    *,
    user: User,
    document_id: UUID,
    data: DocumentUpdate,
) -> Document | None:
    document = await get_user_document(
        session,
        user=user,
        document_id=document_id,
    )

    if document is None:
        return None

    fields_set = data.model_fields_set

    if "title" in fields_set:
        if data.title is None:
            raise InvalidDocumentUpdateError(
                "Document title cannot be null"
            )

        document.title = data.title

    if "content" in fields_set:
        if document.source_type != "text":
            raise UnsupportedDocumentContentUpdateError(
                "File document content cannot be updated"
            )

        document.content = data.content
        document.status = DocumentStatus.PENDING.value

    return await save_document(
        session,
        document=document,
    )


# ============================================================
# Atomic File Reprocessing Claim
# ============================================================


async def claim_user_file_reprocessing(
    session: AsyncSession,
    *,
    user: User,
    document_id: UUID,
) -> bool:
    """
    Atomically claim a file document for reprocessing.

    Only documents in READY or FAILED status with a
    valid storage key are eligible.

    The repository performs a conditional UPDATE to
    prevent multiple concurrent requests from claiming
    the same document.
    """

    return await claim_file_document_reprocessing(
        session,
        document_id=document_id,
        user_id=user.id,
    )


async def recover_user_stale_file_processing(
    session: AsyncSession,
    *,
    user: User,
    document_id: UUID,
) -> bool:
    """Recover an expired processing lease owned by this user."""

    return await recover_stale_file_processing(
        session,
        document_id=document_id,
        user_id=user.id,
    )


async def delete_workspace_document(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    document_id: UUID,
) -> bool:
    """Delete a document safely within a workspace."""
    document = await get_document_by_id_and_workspace_for_update(
        session,
        document_id=document_id,
        workspace_id=workspace_id,
    )

    if document is None:
        await session.rollback()
        return False

    if document.status == DocumentStatus.PROCESSING.value:
        cutoff = await session.scalar(
            select(func.now() - text("INTERVAL '5 minutes'"))
        )

        heartbeat_at = document.processing_heartbeat_at
        started_at = document.processing_started_at

        lease_expired = (
            (
                heartbeat_at is not None
                and heartbeat_at < cutoff
            )
            or (
                heartbeat_at is None
                and (
                    started_at is None
                    or started_at < cutoff
                )
            )
        )

        if not lease_expired:
            await session.rollback()
            raise DocumentProcessingError(
                "Document is currently processing"
            )

    storage_key = document.storage_key

    await delete_document(
        session,
        document=document,
    )

    if storage_key:
        try:
            delete_stored_file(storage_key)
        except (OSError, InvalidStorageKeyError):
            logger.exception(
                "Failed to clean up source file for document %s",
                document_id,
            )

    return True


async def update_workspace_document(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    document_id: UUID,
    data: DocumentUpdate,
) -> Document | None:
    document = await get_workspace_document(
        session,
        workspace_id=workspace_id,
        document_id=document_id,
    )

    if document is None:
        return None

    fields_set = data.model_fields_set

    if "title" in fields_set:
        if data.title is None:
            raise InvalidDocumentUpdateError(
                "Document title cannot be null"
            )
        document.title = data.title

    if "content" in fields_set:
        if document.source_type != "text":
            raise UnsupportedDocumentContentUpdateError(
                "File document content cannot be updated"
            )
        document.content = data.content
        document.status = DocumentStatus.PENDING.value

    return await save_document(
        session,
        document=document,
    )


async def claim_workspace_file_reprocessing_service(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    document_id: UUID,
) -> bool:
    return await claim_workspace_file_reprocessing(
        session,
        document_id=document_id,
        workspace_id=workspace_id,
    )


async def recover_workspace_stale_file_processing_service(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    document_id: UUID,
) -> bool:
    return await recover_workspace_stale_file_processing(
        session,
        document_id=document_id,
        workspace_id=workspace_id,
    )

