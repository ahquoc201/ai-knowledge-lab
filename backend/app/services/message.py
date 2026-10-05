from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.message_role import MessageRole
from app.models.message import Message
from app.models.user import User
from app.repositories.message import (
    create_message,
    list_messages_by_conversation_for_user,
)
from app.services.conversation import get_user_conversation


async def create_conversation_message(
    session: AsyncSession,
    *,
    user: User,
    conversation_id: UUID,
    role: MessageRole,
    content: str,
) -> Message | None:
    conversation = await get_user_conversation(
        session,
        user=user,
        conversation_id=conversation_id,
    )

    if conversation is None:
        return None

    return await create_message(
        session,
        conversation=conversation,
        role=role,
        content=content,
    )


async def list_conversation_messages(
    session: AsyncSession,
    *,
    user: User,
    conversation_id: UUID,
) -> list[Message] | None:
    conversation = await get_user_conversation(
        session,
        user=user,
        conversation_id=conversation_id,
    )

    if conversation is None:
        return None

    return await list_messages_by_conversation_for_user(
        session,
        conversation_id=conversation.id,
        user_id=user.id,
    )