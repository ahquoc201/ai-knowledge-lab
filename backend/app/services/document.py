from sqlalchemy.ext.asyncio import AsyncSession

from app.core.document_status import DocumentStatus
from app.models.document import Document
from app.models.user import User
from app.repositories.document import (
    create_document,
    delete_document,
    get_document_by_id_for_user,
    list_documents_by_user,
    save_document,
    update_document_content,
    update_document_status,
)
from app.schemas.document import DocumentCreate, DocumentUpdate


async def create_user_document(
    session: AsyncSession,
    *,
    user: User,
    data: DocumentCreate,
) -> Document:
    return await create_document(
        session,
        user_id=user.id,
        title=data.title,
        content=data.content,
        source_type=data.source_type,
        source_name=data.source_name,
        mime_type=data.mime_type,
    )


async def list_user_documents(
    session: AsyncSession,
    *,
    user: User,
    search: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Document]:
    return await list_documents_by_user(
        session,
        user.id,
        search=search,
        status=status,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )

from uuid import UUID


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

async def set_document_status(
    session: AsyncSession,
    *,
    document: Document,
    status: DocumentStatus,
) -> Document:
    return await update_document_status(
        session,
        document=document,
        status=status.value,
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

async def delete_user_document(
    session: AsyncSession,
    *,
    user: User,
    document_id: UUID,
) -> bool:
    document = await get_user_document(
        session,
        user=user,
        document_id=document_id,
    )

    if document is None:
        return False

    await delete_document(
        session,
        document=document,
    )

    return True

class UnsupportedDocumentContentUpdateError(ValueError):
    pass


class InvalidDocumentUpdateError(ValueError):
    pass


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