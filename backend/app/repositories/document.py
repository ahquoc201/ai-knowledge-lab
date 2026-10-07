from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


async def create_document(
    session: AsyncSession,
    *,
    user_id: UUID,
    title: str,
    content: str | None,
    source_type: str,
    source_name: str | None,
    mime_type: str | None,
) -> Document:
    document = Document(
        user_id=user_id,
        title=title,
        content=content,
        source_type=source_type,
        source_name=source_name,
        mime_type=mime_type,
    )

    session.add(document)
    await session.commit()
    await session.refresh(document)

    return document


async def list_documents_by_user(
    session: AsyncSession,
    user_id: UUID,
) -> list[Document]:
    result = await session.execute(
        select(Document)
        .where(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
    )

    return list(result.scalars().all())

async def get_document_by_id_for_user(
    session: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
) -> Document | None:
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
    )

    return result.scalar_one_or_none()

async def update_document_status(
    session: AsyncSession,
    *,
    document: Document,
    status: str,
) -> Document:
    document.status = status

    await session.commit()
    await session.refresh(document)

    return document

async def update_document_content(
    session: AsyncSession,
    *,
    document: Document,
    content: str,
) -> Document:
    document.content = content

    await session.commit()
    await session.refresh(document)

    return document

async def delete_document(
    session: AsyncSession,
    *,
    document: Document,
) -> None:
    await session.delete(document)
    await session.commit()

async def save_document(
    session: AsyncSession,
    *,
    document: Document,
) -> Document:
    await session.commit()
    await session.refresh(document)

    return document