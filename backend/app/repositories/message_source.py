from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
        select(MessageSource)
        .where(MessageSource.message_id == message_id)
        .order_by(MessageSource.source_index.asc())
    )

    return list(result.scalars().all())

async def list_message_sources_by_message_ids(
    session: AsyncSession,
    *,
    message_ids: list[UUID],
) -> list[MessageSource]:
    if not message_ids:
        return []

    result = await session.execute(
        select(MessageSource)
        .where(
            MessageSource.message_id.in_(message_ids)
        )
        .order_by(
            MessageSource.message_id.asc(),
            MessageSource.source_index.asc(),
        )
    )

    return list(result.scalars().all())