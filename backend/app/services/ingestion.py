import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.document_status import DocumentStatus
from app.models.document import Document
from app.models.user import User
from app.repositories.document import mark_processing_run_failed
from app.repositories.document_chunk import replace_document_content_and_chunks
from app.schemas.document import DocumentCreate
from app.services.document import (
    create_user_document,
    set_document_status,
)
from app.services.document_chunk import build_embedded_document_chunks
from app.services.file_extractor import extract_text


async def process_document(
    session: AsyncSession,
    *,
    document: Document,
    data: bytes,
    processing_run_id: UUID | None = None,
) -> Document:
    document_id = document.id

    if processing_run_id is None:
        # Legacy ingestion path without a processing lease.
        await set_document_status(
            session,
            document=document,
            status=DocumentStatus.PROCESSING,
        )
    else:
        # The Celery worker has already claimed PROCESSING.
        # Keep the owner ID before any possible rollback.
        user_id = document.user_id

    try:
        filename = document.source_name or document.title

        # 1. Extract text without modifying stored content.
        content = await asyncio.to_thread(
            extract_text,
            filename=filename,
            data=data,
        )

        # 2. Prepare chunks and embeddings in memory.
        chunks = await build_embedded_document_chunks(
            document_id=document_id,
            content=content,
        )

        # 3. Validate the lease and atomically replace data.
        await replace_document_content_and_chunks(
            session,
            document=document,
            content=content,
            chunks=chunks,
            processing_run_id=processing_run_id,
        )

    except Exception:
        # Roll back all uncommitted content/chunk changes.
        await session.rollback()

        if processing_run_id is None:
            # Existing ingestion behavior.
            await set_document_status(
                session,
                document=document,
                status=DocumentStatus.FAILED,
            )
        else:
            # Only the current lease owner may mark FAILED.
            # If another worker owns the lease, this is a no-op.
            await mark_processing_run_failed(
                session,
                document_id=document_id,
                user_id=user_id,
                processing_run_id=processing_run_id,
            )

        raise

    return document


async def ingest_file(
    session: AsyncSession,
    *,
    user: User,
    filename: str,
    data: bytes,
    mime_type: str | None = None,
) -> Document:
    document = await create_user_document(
        session,
        user=user,
        data=DocumentCreate(
            title=filename,
            content=None,
            source_type="file",
            source_name=filename,
            mime_type=mime_type,
        ),
    )

    return await process_document(
        session,
        document=document,
        data=data,
    )
