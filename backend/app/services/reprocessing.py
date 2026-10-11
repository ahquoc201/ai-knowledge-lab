
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.document_status import DocumentStatus
from app.models.document import Document
from app.repositories.document_chunk import (
    replace_document_content_and_chunks,
)
from app.services.document import set_document_status
from app.services.document_chunk import build_embedded_document_chunks


class UnsupportedDocumentReprocessingError(ValueError):
    pass


class EmptyDocumentContentError(ValueError):
    pass


async def reprocess_text_document(
    session: AsyncSession,
    *,
    document: Document,
) -> Document:
    """Safely rebuild chunks and embeddings for a text document."""

    if document.source_type != "text":
        raise UnsupportedDocumentReprocessingError(
            "Only text documents can currently be reprocessed"
        )

    if not document.content or not document.content.strip():
        raise EmptyDocumentContentError(
            "Document content is empty"
        )

    content = document.content

    await set_document_status(
        session,
        document=document,
        status=DocumentStatus.PROCESSING,
    )

    try:
        # Build chunks and embeddings without changing
        # existing persisted chunks.
        chunks = await build_embedded_document_chunks(
            document_id=document.id,
            content=content,
        )

        # Replace chunks, embeddings and status
        # in a single database transaction.
        await replace_document_content_and_chunks(
            session,
            document=document,
            content=content,
            chunks=chunks,
        )

    except Exception:
        await session.rollback()

        await set_document_status(
            session,
            document=document,
            status=DocumentStatus.FAILED,
        )

        raise

    # Reload database-generated fields after the atomic commit.
    # In particular, updated_at may be expired by SQLAlchemy.
    await session.refresh(document)

    return document
