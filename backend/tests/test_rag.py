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


@pytest.mark.anyio
async def test_answer_with_rag_skips_llm_when_context_is_empty(
    monkeypatch,
):
    """No retrieved sources must result in a grounded fallback."""

    context = RetrievalContext(
        text="",
        sources=[],
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

    class FailIfCalledLLM:
        async def generate(self, messages):
            raise AssertionError(
                "LLM must not be called when no sources exist"
            )

    result = await answer_with_rag(
        None,
        user_id=uuid4(),
        query="Tài liệu nói gì về Kubernetes?",
        llm=FailIfCalledLLM(),
        limit=5,
    )

    assert result.answer == (
        "Không đủ thông tin trong tài liệu "
        "để trả lời câu hỏi này."
    )
    assert result.sources == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "context_text",
    ["", " \n\t "],
)
async def test_answer_with_rag_skips_llm_when_context_text_is_blank(
    monkeypatch,
    context_text,
):
    """Do not generate answers from blank retrieval context."""

    context = RetrievalContext(
        text=context_text,
        sources=[
            ContextSource(
                source_index=1,
                document_id=uuid4(),
                chunk_id=uuid4(),
                chunk_index=0,
                content="PostgreSQL supports ACID transactions.",
                similarity=0.95,
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

    class FailIfCalledLLM:
        async def generate(self, messages):
            raise AssertionError(
                "LLM must not be called with blank context"
            )

    result = await answer_with_rag(
        None,
        user_id=uuid4(),
        query="PostgreSQL hỗ trợ ACID như thế nào?",
        llm=FailIfCalledLLM(),
    )

    assert result.answer == (
        "Không đủ thông tin trong tài liệu "
        "để trả lời câu hỏi này."
    )
    assert result.sources == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "llm_answer",
    [
        "PostgreSQL hỗ trợ ACID [Source 9].",
        "PostgreSQL hỗ trợ ACID [Source abc].",
        "PostgreSQL hỗ trợ ACID.",
        (
            "PostgreSQL hỗ trợ ACID [Source 1]. "
            "Redis hỗ trợ caching [Source 9]."
        ),
        "PostgreSQL hỗ trợ ACID [source 1].",
    ],
)
async def test_answer_with_rag_rejects_invalid_citations(
    monkeypatch,
    llm_answer,
):
    context = RetrievalContext(
        text="[Source 1]\nPostgreSQL hỗ trợ ACID.",
        sources=[
            ContextSource(
                source_index=1,
                document_id=uuid4(),
                chunk_id=uuid4(),
                chunk_index=0,
                content="PostgreSQL hỗ trợ ACID.",
                similarity=0.95,
            )
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

    llm = FakeLLMProvider(response=llm_answer)

    result = await answer_with_rag(
        None,
        user_id=uuid4(),
        query="PostgreSQL hỗ trợ những gì?",
        llm=llm,
    )

    assert result.answer == (
        "Không thể xác minh câu trả lời "
        "từ tài liệu được truy xuất."
    )
    assert result.sources == []

    # The LLM was called, but its unsupported answer
    # must not be returned to the API.
    assert len(llm.received_messages) == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "llm_answer",
    [
        "Không đủ thông tin trong tài liệu để trả lời câu hỏi này.",
        (
            " \nKhông đủ thông tin trong tài liệu "
            "để trả lời câu hỏi này.\n "
        ),
    ],
)
async def test_answer_with_rag_preserves_explicit_refusal(
    monkeypatch,
    llm_answer,
):
    context = RetrievalContext(
        text="[Source 1]\nPostgreSQL hỗ trợ ACID.",
        sources=[
            ContextSource(
                source_index=1,
                document_id=uuid4(),
                chunk_id=uuid4(),
                chunk_index=0,
                content="PostgreSQL hỗ trợ ACID.",
                similarity=0.95,
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

    llm = FakeLLMProvider(response=llm_answer)

    result = await answer_with_rag(
        None,
        user_id=uuid4(),
        query="PostgreSQL có hỗ trợ tính năng XYZ không?",
        llm=llm,
    )

    assert result.answer == (
        "Không đủ thông tin trong tài liệu "
        "để trả lời câu hỏi này."
    )
    assert result.sources == []

    assert len(llm.received_messages) == 2