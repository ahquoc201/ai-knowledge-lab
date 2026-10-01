from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
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

async def save_chunk_embeddings(
    session: AsyncSession,
    *,
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
) -> list[DocumentChunk]:
    if len(chunks) != len(embeddings):
        raise ValueError(
            "chunks and embeddings must have the same length"
        )

    for chunk, embedding in zip(
        chunks,
        embeddings,
        strict=True,
    ):
        chunk.embedding = embedding

    await session.commit()

    return chunks

async def search_similar_chunks(
    session: AsyncSession,
    *,
    user_id: UUID,
    query_embedding: list[float],
    limit: int = 5,
) -> list[tuple[DocumentChunk, float]]:
    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    ).label("distance")

    result = await session.execute(
        select(
            DocumentChunk,
            distance,
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .where(
            Document.user_id == user_id,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(limit)
    )

    return [
        (chunk, float(chunk_distance))
        for chunk, chunk_distance in result.all()
    ]