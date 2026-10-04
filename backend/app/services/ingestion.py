from sqlalchemy.ext.asyncio import AsyncSession

from app.core.document_status import DocumentStatus
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentCreate
from app.services.document import (
    create_user_document,
    set_document_content,
    set_document_status,
)
from app.services.document_chunk import (
    chunk_document,
    embed_document_chunks,
)
from app.services.file_extractor import extract_text


async def process_document(
    session: AsyncSession,
    *,
    document: Document,
    data: bytes,
) -> Document:
    await set_document_status(
        session,
        document=document,
        status=DocumentStatus.PROCESSING,
    )

    try:
        filename = document.source_name or document.title

        content = extract_text(
            filename=filename,
            data=data,
        )

        await set_document_content(
            session,
            document=document,
            content=content,
        )

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