from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.message_role import MessageRole
from app.models.conversation import Conversation
from app.models.message import Message


async def create_message(
    session: AsyncSession,
    *,
    conversation: Conversation,
    role: MessageRole,
    content: str,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        role=role.value,
        content=content,
    )

    conversation.updated_at = func.now()

    session.add(message)
    await session.commit()
    await session.refresh(message)
    await session.refresh(conversation)

    return message


async def list_messages_by_conversation_for_user(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .join(
            Conversation,
            Conversation.id == Message.conversation_id,
        )
        .where(
            Message.conversation_id == conversation_id,
            Conversation.user_id == user_id,
        )
        .order_by(
            Message.created_at.asc(),
            Message.id.asc(),
        )
    )

    return list(result.scalars().all())

async def list_recent_messages_by_conversation_for_user(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
    limit: int = 10,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .join(
            Conversation,
            Conversation.id == Message.conversation_id,
        )
        .where(
            Message.conversation_id == conversation_id,
            Conversation.user_id == user_id,
        )
        .order_by(
            Message.created_at.desc(),
            Message.id.desc(),
        )
        .limit(limit)
    )

    messages = list(result.scalars().all())
    messages.reverse()

    return messages