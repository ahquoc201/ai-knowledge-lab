from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.message_source import MessageSource
from app.repositories.message_source import (
    list_message_sources,
    list_message_sources_by_message_ids,
    save_message_sources,
)
from app.services.context_builder import ContextSource


async def save_assistant_message_sources(
    session: AsyncSession,
    *,
    message: Message,
    sources: list[ContextSource],
) -> list[MessageSource]:
    message_sources = [
        MessageSource(
            message_id=message.id,
            source_index=source.source_index,
            document_id=source.document_id,
            chunk_id=source.chunk_id,
            chunk_index=source.chunk_index,
            content=source.content,
            similarity=source.similarity,
        )
        for source in sources
    ]

    return await save_message_sources(
        session,
        sources=message_sources,
    )


async def get_message_sources(
    session: AsyncSession,
    *,
    message: Message,
) -> list[MessageSource]:
    return await list_message_sources(
        session,
        message_id=message.id,
    )

async def get_message_sources_by_message_ids(
    session: AsyncSession,
    *,
    message_ids: list[UUID],
) -> dict[UUID, list[MessageSource]]:
    sources = await list_message_sources_by_message_ids(
        session,
        message_ids=message_ids,
    )

    grouped_sources: dict[UUID, list[MessageSource]] = {
        message_id: []
        for message_id in message_ids
    }

    for source in sources:
        grouped_sources[source.message_id].append(source)

    return grouped_sources