from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk import replace_document_chunks
from app.services.chunking import chunk_text


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