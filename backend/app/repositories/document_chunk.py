from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk


async def replace_document_chunks(
    session: AsyncSession,
    *,
    document_id: UUID,
    chunks: list[DocumentChunk],
) -> list[DocumentChunk]:
    await session.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
    )

    session.add_all(chunks)
    await session.commit()

    return chunks


async def list_document_chunks(
    session: AsyncSession,
    document_id: UUID,
) -> list[DocumentChunk]:
    result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )

    return list(result.scalars().all())