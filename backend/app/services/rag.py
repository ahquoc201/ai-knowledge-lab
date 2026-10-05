from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMMessage, LLMProvider
from app.services.context_builder import ContextSource
from app.services.rag_prompt import build_rag_messages
from app.services.retrieval import retrieve_context


@dataclass(frozen=True, slots=True)
class RAGResult:
    answer: str
    sources: list[ContextSource]


async def answer_with_rag(
    session: AsyncSession,
    *,
    user_id: UUID,
    query: str,
    llm: LLMProvider,
    limit: int = 5,
    history: list[LLMMessage] | None = None,
) -> RAGResult:
    context = await retrieve_context(
        session,
        user_id=user_id,
        query=query,
        limit=limit,
    )

    messages = build_rag_messages(
        query=query,
        context=context,
        history=history,
    )

    answer = await llm.generate(messages)

    return RAGResult(
        answer=answer,
        sources=context.sources,
    )