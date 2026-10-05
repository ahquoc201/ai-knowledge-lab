from uuid import uuid4

import pytest

from app.llm.base import LLMMessage
from app.services.context_builder import (
    ContextSource,
    RetrievalContext,
)
from app.services.rag import answer_with_rag
from tests.fakes import FakeLLMProvider


@pytest.mark.anyio
async def test_answer_with_rag_builds_prompt_and_returns_sources(
    monkeypatch,
):
    document_id = uuid4()
    chunk_id = uuid4()

    context = RetrievalContext(
        text=(
            "[Source 1]\n"
            "PostgreSQL hỗ trợ transaction và lưu trữ dữ liệu."
        ),
        sources=[
            ContextSource(
                source_index=1,
                document_id=document_id,
                chunk_id=chunk_id,
                chunk_index=0,
                content=(
                    "PostgreSQL hỗ trợ transaction "
                    "và lưu trữ dữ liệu."
                ),
                similarity=0.93,
            ),
        ],
    )

    async def fake_retrieve_context(
        session,
        *,
        user_id,
        query,
        limit,
    ):
        return context

    monkeypatch.setattr(
        "app.services.rag.retrieve_context",
        fake_retrieve_context,
    )

    llm = FakeLLMProvider(
        response=(
            "PostgreSQL hỗ trợ lưu trữ dữ liệu "
            "và transaction [Source 1]."
        ),
    )

    history = [
        LLMMessage(
            role="user",
            content="PostgreSQL là gì?",
        ),
        LLMMessage(
            role="assistant",
            content="Đây là một hệ quản trị cơ sở dữ liệu.",
        ),
    ]

    result = await answer_with_rag(
        None,
        user_id=uuid4(),
        query="PostgreSQL dùng để làm gì?",
        llm=llm,
        limit=5,
        history=history,
    )

    assert result.answer == (
        "PostgreSQL hỗ trợ lưu trữ dữ liệu "
        "và transaction [Source 1]."
    )

    assert result.sources == context.sources

    assert len(llm.received_messages) == 2
    assert llm.received_messages[0].role == "system"
    assert llm.received_messages[1].role == "user"

    assert "[Source 1]" in llm.received_messages[1].content
    assert (
        "PostgreSQL dùng để làm gì?"
        in llm.received_messages[1].content
    )

    assert (
        "user: PostgreSQL là gì?"
        in llm.received_messages[1].content
    )

    assert (
        "assistant: Đây là một hệ quản trị cơ sở dữ liệu."
        in llm.received_messages[1].content
    )