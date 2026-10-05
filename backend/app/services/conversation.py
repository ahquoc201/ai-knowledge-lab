from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.user import User
from app.repositories.conversation import (
    create_conversation,
    delete_conversation,
    get_conversation_by_id_for_user,
    list_conversations_by_user,
    update_conversation_title,
)


async def create_user_conversation(
    session: AsyncSession,
    *,
    user: User,
    title: str | None = None,
) -> Conversation:
    return await create_conversation(
        session,
        user_id=user.id,
        title=title,
    )


async def list_user_conversations(
    session: AsyncSession,
    *,
    user: User,
) -> list[Conversation]:
    return await list_conversations_by_user(
        session,
        user.id,
    )


async def get_user_conversation(
    session: AsyncSession,
    *,
    user: User,
    conversation_id: UUID,
) -> Conversation | None:
    return await get_conversation_by_id_for_user(
        session,
        conversation_id=conversation_id,
        user_id=user.id,
    )

async def update_user_conversation(
    session: AsyncSession,
    *,
    user: User,
    conversation_id: UUID,
    title: str,
) -> Conversation | None:
    conversation = await get_user_conversation(
        session,
        user=user,
        conversation_id=conversation_id,
    )

    if conversation is None:
        return None

    return await update_conversation_title(
        session,
        conversation=conversation,
        title=title,
    )


async def delete_user_conversation(
    session: AsyncSession,
    *,
    user: User,
    conversation_id: UUID,
) -> bool:
    conversation = await get_user_conversation(
        session,
        user=user,
        conversation_id=conversation_id,
    )

    if conversation is None:
        return False

    await delete_conversation(
        session,
        conversation=conversation,
    )

    return True