from uuid import uuid4

import pytest

from app.llm.base import LLMMessage
from app.services.context_builder import (
    ContextSource,
    RetrievalContext,
)
from app.services.rag_prompt import (
    SYSTEM_PROMPT,
    build_bounded_history,
    build_rag_messages,
)


def test_build_rag_messages_with_context():
    context = RetrievalContext(
        text=(
            "[Source 1]\n"
            "PostgreSQL hỗ trợ transaction.\n\n"
            "[Source 2]\n"
            "pgvector hỗ trợ semantic search."
        ),
        sources=[
            ContextSource(
                source_index=1,
                document_id=uuid4(),
                chunk_id=uuid4(),
                chunk_index=0,
                content="PostgreSQL hỗ trợ transaction.",
                similarity=0.91,
            ),
            ContextSource(
                source_index=2,
                document_id=uuid4(),
                chunk_id=uuid4(),
                chunk_index=1,
                content="pgvector hỗ trợ semantic search.",
                similarity=0.86,
            ),
        ],
    )

    messages = build_rag_messages(
        query="PostgreSQL và pgvector dùng để làm gì?",
        context=context,
    )

    assert len(messages) == 2

    assert messages[0].role == "system"
    assert messages[0].content == SYSTEM_PROMPT

    assert messages[1].role == "user"

    assert "[Source 1]" in messages[1].content
    assert "[Source 2]" in messages[1].content
    assert "PostgreSQL hỗ trợ transaction." in messages[1].content
    assert "pgvector hỗ trợ semantic search." in messages[1].content

    assert (
        "PostgreSQL và pgvector dùng để làm gì?"
        in messages[1].content
    )


def test_build_rag_messages_with_empty_context():
    context = RetrievalContext(
        text="",
        sources=[],
    )

    messages = build_rag_messages(
        query="Thông tin này có trong tài liệu không?",
        context=context,
    )

    assert len(messages) == 2

    assert (
        "(No relevant context was retrieved.)"
        in messages[1].content
    )

    assert (
        "Thông tin này có trong tài liệu không?"
        in messages[1].content
    )

def test_build_rag_messages_with_conversation_history():
    context = RetrievalContext(
        text="[Source 1]\nPostgreSQL hỗ trợ transaction.",
        sources=[],
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

    messages = build_rag_messages(
        query="Nó hỗ trợ gì?",
        context=context,
        history=history,
    )

    assert len(messages) == 2

    assert "user: PostgreSQL là gì?" in messages[1].content
    assert (
        "assistant: Đây là một hệ quản trị cơ sở dữ liệu."
        in messages[1].content
    )
    assert "[Source 1]" in messages[1].content
    assert "Nó hỗ trợ gì?" in messages[1].content


def extract_history_section(messages: list[LLMMessage]) -> str:
    """Extract only the conversation-history part of the prompt."""

    prompt = messages[1].content

    prefix = (
        "Conversation history "
        "(for conversational context only, not factual evidence):\n\n"
    )

    return (
        prompt.split(prefix, maxsplit=1)[1]
        .split("\n\nRetrieved context:", maxsplit=1)[0]
    )


def make_test_context() -> RetrievalContext:
    return RetrievalContext(
        text="[Source 1]\nPostgreSQL supports transactions.",
        sources=[],
    )


def test_history_budget_keeps_most_recent_messages():
    history = [
        LLMMessage(role="user", content="oldest"),
        LLMMessage(role="assistant", content="middle"),
        LLMMessage(role="user", content="newest"),
    ]

    messages = build_rag_messages(
        query="Explain transactions.",
        context=make_test_context(),
        history=history,
        max_history_chars=30,
    )

    assert extract_history_section(messages) == (
        "assistant: middle\n"
        "user: newest"
    )


def test_history_budget_truncates_latest_message():
    history = [
        LLMMessage(
            role="user",
            content="abcdefghijklmnopqrst",
        ),
    ]

    messages = build_rag_messages(
        query="Explain transactions.",
        context=make_test_context(),
        history=history,
        max_history_chars=20,
    )

    assert extract_history_section(messages) == (
        "user: ghijklmnopqrst"
    )


def test_history_budget_has_default_limit():
    history = [
        LLMMessage(
            role="user",
            content="x" * 5000,
        ),
    ]

    messages = build_rag_messages(
        query="Explain transactions.",
        context=make_test_context(),
        history=history,
    )

    history_text = extract_history_section(messages)

    assert len(history_text) == 4000
    assert history_text.startswith("user: ")
    assert history_text.endswith("x" * 3994)


@pytest.mark.parametrize(
    ("max_history_chars", "error_type"),
    [
        (0, ValueError),
        (-1, ValueError),
        (True, TypeError),
        (1.5, TypeError),
    ],
)
def test_history_budget_rejects_invalid_values(
    max_history_chars,
    error_type,
):
    with pytest.raises(error_type):
        build_rag_messages(
            query="Explain transactions.",
            context=make_test_context(),
            history=[],
            max_history_chars=max_history_chars,
        )


@pytest.mark.parametrize(
    ("budget", "expected"),
    [
        (
            29,
            "user: older\nassistant: recent",
        ),
        (
            28,
            "assistant: recent",
        ),
        (
            17,
            "assistant: recent",
        ),
        (
            16,
            "assistant: ecent",
        ),
        (
            11,
            "",
        ),
    ],
)
def test_history_budget_exact_boundaries(
    budget,
    expected,
):
    history = [
        LLMMessage(
            role="user",
            content="older",
        ),
        LLMMessage(
            role="assistant",
            content="recent",
        ),
    ]

    result = build_bounded_history(
        history,
        max_chars=budget,
    )

    assert result == expected
    assert len(result) <= budget


@pytest.mark.parametrize(
    ("budget", "expected"),
    [
        (27, "(No previous conversation.)"),
        (26, ""),
    ],
)
def test_history_budget_empty_history_boundaries(
    budget,
    expected,
):
    result = build_bounded_history(
        [],
        max_chars=budget,
    )

    assert result == expected
    assert len(result) <= budget


def test_history_budget_preserves_chronological_order():
    history = [
        LLMMessage(role="user", content="first"),
        LLMMessage(role="assistant", content="second"),
        LLMMessage(role="user", content="third"),
    ]

    result = build_bounded_history(
        history,
        max_chars=100,
    )

    assert result == (
        "user: first\n"
        "assistant: second\n"
        "user: third"
    )


def test_system_prompt_requires_canonical_refusal():
    """The LLM must know the exact refusal accepted by RAG."""

    refusal_message = (
        "Không đủ thông tin trong tài liệu "
        "để trả lời câu hỏi này."
    )

    assert refusal_message in SYSTEM_PROMPT
    assert (
        "Do not add citations to the refusal."
        in SYSTEM_PROMPT
    )