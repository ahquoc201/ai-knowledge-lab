from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.chat_history import get_conversation_history


@pytest.mark.anyio
async def test_get_conversation_history_returns_recent_messages(
    monkeypatch,
):
    user = SimpleNamespace(id=uuid4())
    conversation = SimpleNamespace(id=uuid4())

    messages = [
        SimpleNamespace(
            role="user",
            content="Câu hỏi trước",
        ),
        SimpleNamespace(
            role="assistant",
            content="Câu trả lời trước",
        ),
    ]

    async def fake_get_user_conversation(
        session,
        *,
        user,
        conversation_id,
    ):
        assert conversation_id == conversation.id
        return conversation

    async def fake_list_recent_messages(
        session,
        *,
        conversation_id,
        user_id,
        limit,
    ):
        assert conversation_id == conversation.id
        assert user_id == user.id
        assert limit == 10

        return messages

    monkeypatch.setattr(
        "app.services.chat_history.get_user_conversation",
        fake_get_user_conversation,
    )

    monkeypatch.setattr(
        (
            "app.services.chat_history."
            "list_recent_messages_by_conversation_for_user"
        ),
        fake_list_recent_messages,
    )

    history = await get_conversation_history(
        None,
        user=user,
        conversation_id=conversation.id,
    )

    assert history is not None
    assert len(history) == 2

    assert history[0].role == "user"
    assert history[0].content == "Câu hỏi trước"

    assert history[1].role == "assistant"
    assert history[1].content == "Câu trả lời trước"


@pytest.mark.anyio
async def test_get_conversation_history_returns_none_for_unknown_conversation(
    monkeypatch,
):
    user = SimpleNamespace(id=uuid4())

    async def fake_get_user_conversation(
        session,
        *,
        user,
        conversation_id,
    ):
        return None

    monkeypatch.setattr(
        "app.services.chat_history.get_user_conversation",
        fake_get_user_conversation,
    )

    history = await get_conversation_history(
        None,
        user=user,
        conversation_id=uuid4(),
    )

    assert history is None