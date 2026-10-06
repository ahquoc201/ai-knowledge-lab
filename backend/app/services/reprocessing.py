from sqlalchemy.ext.asyncio import AsyncSession

from app.core.document_status import DocumentStatus
from app.models.document import Document
from app.services.document import set_document_status
from app.services.document_chunk import (
    chunk_document,
    embed_document_chunks,
)


class UnsupportedDocumentReprocessingError(ValueError):
    pass


class EmptyDocumentContentError(ValueError):
    pass


async def reprocess_text_document(
    session: AsyncSession,
    *,
    document: Document,
) -> Document:
    if document.source_type != "text":
        raise UnsupportedDocumentReprocessingError(
            "Only text documents can currently be reprocessed"
        )

    if not document.content or not document.content.strip():
        raise EmptyDocumentContentError(
            "Document content is empty"
        )

    await set_document_status(
        session,
        document=document,
        status=DocumentStatus.PROCESSING,
    )

    try:
        await chunk_document(
            session,
            document=document,
        )

        await embed_document_chunks(
            session,
            document_id=document.id,
        )

        await set_document_status(
            session,
            document=document,
            status=DocumentStatus.READY,
        )
    except Exception:
        await session.rollback()

        await set_document_status(
            session,
            document=document,
            status=DocumentStatus.FAILED,
        )

        raise

    return document