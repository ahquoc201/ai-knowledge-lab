from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMMessage, LLMProvider
from app.services.citation_validation import validate_answer_citations
from app.services.context_builder import ContextSource
from app.services.rag_prompt import (
    INSUFFICIENT_CONTEXT_ANSWER,
    build_rag_messages,
)
from app.services.retrieval import retrieve_context


@dataclass(frozen=True, slots=True)
class RAGResult:
    answer: str
    sources: list[ContextSource]


async def answer_with_rag(
    session: AsyncSession,
    *,
    user_id: UUID | None = None,
    workspace_id: UUID | None = None,
    query: str,
    llm: LLMProvider,
    limit: int = 5,
    history: list[LLMMessage] | None = None,
) -> RAGResult:
    import inspect

    retrieval_kwargs = {
        "session": session,
        "query": query,
        "limit": limit,
    }
    if user_id is not None:
        retrieval_kwargs["user_id"] = user_id
    if workspace_id is not None and "workspace_id" in inspect.signature(retrieve_context).parameters:
        retrieval_kwargs["workspace_id"] = workspace_id

    context = await retrieve_context(**retrieval_kwargs)


    # Only generate an answer when usable evidence exists.
    if not context.sources or not context.text.strip():
        return RAGResult(
            answer=INSUFFICIENT_CONTEXT_ANSWER,
            sources=[],
        )

    messages = build_rag_messages(
        query=query,
        context=context,
        history=history,
    )

    answer = await llm.generate(messages)

    if answer.strip() == INSUFFICIENT_CONTEXT_ANSWER:
        return RAGResult(
            answer=INSUFFICIENT_CONTEXT_ANSWER,
            sources=[],
        )

    validation = validate_answer_citations(
        answer,
        context.sources,
    )

    # Do not expose answers with missing or invalid citations.
    if not validation.is_valid:
        return RAGResult(
            answer=(
                "Không thể xác minh câu trả lời "
                "từ tài liệu được truy xuất."
            ),
            sources=[],
        )

    return RAGResult(
        answer=answer,
        sources=context.sources,
    )