from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation


async def create_conversation(
    session: AsyncSession,
    *,
    user_id: UUID,
    title: str | None = None,
) -> Conversation:
    conversation = Conversation(
        user_id=user_id,
        title=title,
    )

    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)

    return conversation


async def list_conversations_by_user(
    session: AsyncSession,
    user_id: UUID,
) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )

    return list(result.scalars().all())


async def get_conversation_by_id_for_user(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
) -> Conversation | None:
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )

    return result.scalar_one_or_none()

async def update_conversation_title(
    session: AsyncSession,
    *,
    conversation: Conversation,
    title: str,
) -> Conversation:
    conversation.title = title

    await session.commit()
    await session.refresh(conversation)

    return conversation


async def delete_conversation(
    session: AsyncSession,
    *,
    conversation: Conversation,
) -> None:
    await session.delete(conversation)
    await session.commit()