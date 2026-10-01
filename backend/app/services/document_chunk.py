from uuid import UUID

from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk import (
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