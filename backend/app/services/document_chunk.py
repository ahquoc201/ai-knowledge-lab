from uuid import UUID

from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk import (
    ensure_manual_chunk_write_allowed,
    list_document_chunks,
    replace_document_chunks,
    save_chunk_embeddings,
)
from app.services.chunking import chunk_text
from app.services.embedding import get_embedding_service


async def chunk_document(
    session: AsyncSession,
    *,
    document: Document,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> list[DocumentChunk]:
    text_chunks = chunk_text(
        document.content or "",
        chunk_size=chunk_size,
        overlap=overlap,
    )

    document_chunks = [
        DocumentChunk(
            document_id=document.id,
            chunk_index=chunk.index,
            content=chunk.content,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
        )
        for chunk in text_chunks
    ]

    return await replace_document_chunks(
        session,
        document_id=document.id,
        chunks=document_chunks,
    )

def _embed_passages(
    texts: list[str],
) -> list[list[float]]:
    service = get_embedding_service()
    return service.embed_passages(texts)

async def build_embedded_document_chunks(
    *,
    document_id: UUID,
    content: str,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> list[DocumentChunk]:
    """Prepare fully embedded chunks without writing to the database."""
    text_chunks = chunk_text(
        content,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    if not text_chunks:
        return []

    texts = [chunk.content for chunk in text_chunks]

    embeddings = await to_thread.run_sync(
        _embed_passages,
        texts,
    )

    if len(text_chunks) != len(embeddings):
        raise ValueError(
            "chunks and embeddings must have the same length"
        )

    return [
        DocumentChunk(
            document_id=document_id,
            chunk_index=chunk.index,
            content=chunk.content,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            embedding=embedding,
        )
        for chunk, embedding in zip(
            text_chunks,
            embeddings,
            strict=True,
        )
    ]


async def embed_document_chunks(
    session: AsyncSession,
    *,
    document_id: UUID,
) -> list[DocumentChunk]:
    chunks = await list_document_chunks(
        session,
        document_id=document_id,
    )

    if not chunks:
        await ensure_manual_chunk_write_allowed(
            session,
            document_id=document_id,
        )
        return []

    texts = [
        chunk.content
        for chunk in chunks
    ]

    embeddings = await to_thread.run_sync(
        _embed_passages,
        texts,
    )

    return await save_chunk_embeddings(
        session,
        chunks=chunks,
        embeddings=embeddings,
    )