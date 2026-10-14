
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.document_status import DocumentStatus
from app.models.document import Document
from app.models.document_chunk import DocumentChunk


class ProcessingLeaseLostError(RuntimeError):
    """The worker no longer owns the processing lease."""


class DocumentChunkWriteConflictError(RuntimeError):
    """A concurrent operation prevents modifying chunks."""


async def _lock_manual_writable_document(
    session: AsyncSession,
    *,
    document_id: UUID,
) -> None:
    """Lock the parent document and validate manual write access."""

    result = await session.execute(
        select(
            Document.status,
            Document.source_type,
        )
        .where(Document.id == document_id)
        .with_for_update()
    )

    row = result.one_or_none()

    if row is None:
        await session.rollback()
        raise DocumentChunkWriteConflictError(
            "Document is no longer available"
        )

    document_status, source_type = row

    is_processing = (
        document_status == DocumentStatus.PROCESSING.value
    )

    is_pending_file = (
        source_type == "file"
        and document_status == DocumentStatus.PENDING.value
    )

    if is_processing or is_pending_file:
        await session.rollback()
        raise DocumentChunkWriteConflictError(
            "Document is being processed"
        )

async def ensure_manual_chunk_write_allowed(
    session: AsyncSession,
    *,
    document_id: UUID,
) -> None:
    """Validate write access even when no chunks exist."""

    await _lock_manual_writable_document(
        session,
        document_id=document_id,
    )

    # No data is modified. Release the document lock.
    await session.commit()


async def replace_document_chunks(
    session: AsyncSession,
    *,
    document_id: UUID,
    chunks: list[DocumentChunk],
) -> list[DocumentChunk]:
    """Replace chunks while holding the document write lock."""

    if any(
        chunk.document_id != document_id
        for chunk in chunks
    ):
        raise ValueError(
            "All chunks must belong to the target document"
        )

    await _lock_manual_writable_document(
        session,
        document_id=document_id,
    )

    await session.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
    )

    session.add_all(chunks)

    await session.commit()

    return chunks


async def replace_document_content_and_chunks(
    session: AsyncSession,
    *,
    document: Document,
    content: str,
    chunks: list[DocumentChunk],
    processing_run_id: UUID | None = None,
) -> list[DocumentChunk]:
    """Atomically replace content and chunks with lease validation."""

    if any(
        chunk.document_id != document.id
        for chunk in chunks
    ):
        raise ValueError(
            "All chunks must belong to the target document"
        )

    if processing_run_id is not None:
        result = await session.execute(
            select(Document.id)
            .where(
                Document.id == document.id,
                Document.user_id == document.user_id,
                Document.status == DocumentStatus.PROCESSING.value,
                Document.processing_run_id == processing_run_id,
            )
            .with_for_update()
        )

        if result.scalar_one_or_none() is None:
            raise ProcessingLeaseLostError(
                "Document processing lease is no longer valid"
            )

    await session.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document.id
        )
    )

    session.add_all(chunks)

    document.content = content
    document.status = DocumentStatus.READY.value

    document.processing_run_id = None
    document.processing_started_at = None
    document.processing_heartbeat_at = None

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
    """Save embeddings only if the chunk snapshot is unchanged."""

    if len(chunks) != len(embeddings):
        raise ValueError(
            "chunks and embeddings must have the same length"
        )

    if not chunks:
        return []

    document_ids = {
        chunk.document_id
        for chunk in chunks
    }

    if len(document_ids) != 1:
        raise ValueError(
            "All chunks must belong to the same document"
        )

    document_id = chunks[0].document_id

    # Capture the snapshot used to calculate embeddings.
    expected_chunks = {
        chunk.id: (
            chunk.content,
            chunk.chunk_index,
            chunk.char_start,
            chunk.char_end,
        )
        for chunk in chunks
    }

    if len(expected_chunks) != len(chunks):
        raise ValueError("Duplicate chunk IDs")

    # Lock the parent document AFTER embedding computation.
    # No expensive AI work is performed while holding the lock.
    await _lock_manual_writable_document(
        session,
        document_id=document_id,
    )

    # Query scalar columns to obtain fresh database values,
    # avoiding stale ORM identity-map data.
    result = await session.execute(
        select(
            DocumentChunk.id,
            DocumentChunk.content,
            DocumentChunk.chunk_index,
            DocumentChunk.char_start,
            DocumentChunk.char_end,
        ).where(
            DocumentChunk.document_id == document_id
        )
    )

    actual_chunks = {
        row.id: (
            row.content,
            row.chunk_index,
            row.char_start,
            row.char_end,
        )
        for row in result.all()
    }

    if actual_chunks != expected_chunks:
        await session.rollback()
        raise DocumentChunkWriteConflictError(
            "Document chunks changed during embedding"
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
    user_id: UUID | None = None,
    workspace_id: UUID | None = None,
    query_embedding: list[float],
    limit: int = 5,
) -> list[tuple[DocumentChunk, float, str]]:
    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    ).label("distance")

    query = (
        select(
            DocumentChunk,
            distance,
            Document.title,
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
    )

    if workspace_id is not None:
        query = query.where(
            Document.workspace_id == workspace_id,
            DocumentChunk.embedding.is_not(None),
        )
    elif user_id is not None:
        query = query.where(
            Document.user_id == user_id,
            DocumentChunk.embedding.is_not(None),
        )
    else:
        raise ValueError("Either workspace_id or user_id must be provided")

    result = await session.execute(
        query.order_by(distance).limit(limit)
    )

    return [
        (chunk, float(chunk_distance), str(title))
        for chunk, chunk_distance, title in result.all()
    ]

