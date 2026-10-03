from sqlalchemy.ext.asyncio import AsyncSession

from app.core.document_status import DocumentStatus
from app.models.document import Document
from app.models.user import User
from app.repositories.document import (
    create_document,
    get_document_by_id_for_user,
    list_documents_by_user,
    update_document_content,
    update_document_status,
)
from app.schemas.document import DocumentCreate


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
) -> list[Document]:
    return await list_documents_by_user(
        session,
        user.id,
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