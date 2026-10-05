from uuid import uuid4

from app.llm.base import LLMMessage
from app.services.context_builder import (
    ContextSource,
    RetrievalContext,
)
from app.services.rag_prompt import (
    SYSTEM_PROMPT,
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