from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.message_role import MessageRole
from app.llm.base import LLMMessage
from app.models.user import User
from app.repositories.message import (
    list_recent_messages_by_conversation_for_user,
)
from app.services.conversation import get_user_conversation


async def get_conversation_history(
    session: AsyncSession,
    *,
    user: User,
    conversation_id: UUID,
    limit: int = 10,
) -> list[LLMMessage] | None:
    conversation = await get_user_conversation(
        session,
        user=user,
        conversation_id=conversation_id,
    )

    if conversation is None:
        return None

    messages = await list_recent_messages_by_conversation_for_user(
        session,
        conversation_id=conversation.id,
        user_id=user.id,
        limit=limit,
    )

    return [
        LLMMessage(
            role=MessageRole(message.role).value,
            content=message.content,
        )
        for message in messages
    ]