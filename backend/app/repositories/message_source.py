from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.message_source import MessageSource


async def save_message_sources(
    session: AsyncSession,
    *,
    sources: list[MessageSource],
) -> list[MessageSource]:
    if not sources:
        return []

    session.add_all(sources)
    await session.commit()

    return sources


async def list_message_sources(
    session: AsyncSession,
    *,
    message_id: UUID,
) -> list[MessageSource]:
    result = await session.execute(
        select(
            MessageSource,
            Document.title.label("document_title"),
            DocumentChunk.char_start.label("char_start"),
            DocumentChunk.char_end.label("char_end"),
        )
        .outerjoin(Document, MessageSource.document_id == Document.id)
        .outerjoin(DocumentChunk, MessageSource.chunk_id == DocumentChunk.id)
        .where(MessageSource.message_id == message_id)
        .order_by(MessageSource.source_index.asc())
    )

    sources: list[MessageSource] = []
    for row in result.all():
        source = row[0]
        source.document_title = row[1]
        source.char_start = row[2]
        source.char_end = row[3]
        sources.append(source)

    return sources


async def list_message_sources_by_message_ids(
    session: AsyncSession,
    *,
    message_ids: list[UUID],
) -> list[MessageSource]:
    if not message_ids:
        return []

    result = await session.execute(
        select(
            MessageSource,
            Document.title.label("document_title"),
            DocumentChunk.char_start.label("char_start"),
            DocumentChunk.char_end.label("char_end"),
        )
        .outerjoin(Document, MessageSource.document_id == Document.id)
        .outerjoin(DocumentChunk, MessageSource.chunk_id == DocumentChunk.id)
        .where(
            MessageSource.message_id.in_(message_ids)
        )
        .order_by(
            MessageSource.message_id.asc(),
            MessageSource.source_index.asc(),
        )
    )

    sources: list[MessageSource] = []
    for row in result.all():
        source = row[0]
        source.document_title = row[1]
        source.char_start = row[2]
        source.char_end = row[3]
        sources.append(source)

    return sources