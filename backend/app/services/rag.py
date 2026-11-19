import asyncio
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMMessage, LLMProvider
from app.services.citation_validation import validate_answer_citations
from app.services.context_builder import ContextSource
from app.services.rag_observability import (
    elapsed_ms,
    get_rag_observability,
    sanitize_correlation_id,
)
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
    retrieval_mode: str = "dense",
    enable_reranking: bool = False,
) -> RAGResult:
    import inspect

    t_total_start = time.perf_counter()
    cid = sanitize_correlation_id(None)
    obs = get_rag_observability()

    retrieval_ms: float | None = None
    context_ms: float | None = None
    rerank_ms: float | None = None
    rerank_used = False
    rerank_fallback: str | None = None
    llm_ms: float | None = None
    stage = "retrieval"

    try:
        retrieval_kwargs = {
            "session": session,
            "query": query,
            "limit": limit,
        }
        sig_params = inspect.signature(retrieve_context).parameters
        has_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig_params.values())

        if user_id is not None:
            retrieval_kwargs["user_id"] = user_id
        if (workspace_id is not None) and ("workspace_id" in sig_params or has_var_kwargs):
            retrieval_kwargs["workspace_id"] = workspace_id
        if "mode" in sig_params or has_var_kwargs:
            retrieval_kwargs["mode"] = retrieval_mode
        if "enable_reranking" in sig_params or has_var_kwargs:
            retrieval_kwargs["enable_reranking"] = enable_reranking

        context = await retrieve_context(**retrieval_kwargs)
        retrieval_ms = getattr(context, "retrieval_ms", None)
        context_ms = getattr(context, "context_assembly_ms", None)
        rerank_ms = getattr(context, "rerank_ms", None)
        rerank_used = getattr(context, "rerank_used", False)
        rerank_fallback = getattr(context, "rerank_fallback_reason", None)

        # Only generate an answer when usable evidence exists.
        if not context.sources or not context.text.strip():
            obs.record_request(
                correlation_id=cid,
                mode=retrieval_mode,
                stream=False,
                rerank_opt_in=enable_reranking,
                rerank_used=rerank_used,
                rerank_fallback_reason=rerank_fallback,
                status="success",
                retrieval_ms=retrieval_ms,
                rerank_ms=rerank_ms,
                context_assembly_ms=context_ms,
                total_ms=elapsed_ms(t_total_start),
                source_count=0,
            )
            return RAGResult(
                answer=INSUFFICIENT_CONTEXT_ANSWER,
                sources=[],
            )

        stage = "context_assembly"
        messages = build_rag_messages(
            query=query,
            context=context,
            history=history,
        )

        stage = "llm_generation"
        from app.services.inference_governor import get_inference_governor

        governor = get_inference_governor()
        t_llm_start = time.perf_counter()
        async with governor.acquire(caller_info=f"rag_ask:{workspace_id}"):
            answer = await llm.generate(messages)
        llm_ms = elapsed_ms(t_llm_start)

        if answer.strip() == INSUFFICIENT_CONTEXT_ANSWER:
            obs.record_request(
                correlation_id=cid,
                mode=retrieval_mode,
                stream=False,
                rerank_opt_in=enable_reranking,
                rerank_used=rerank_used,
                rerank_fallback_reason=rerank_fallback,
                status="success",
                retrieval_ms=retrieval_ms,
                rerank_ms=rerank_ms,
                context_assembly_ms=context_ms,
                llm_generation_ms=llm_ms,
                total_ms=elapsed_ms(t_total_start),
                source_count=0,
            )
            return RAGResult(
                answer=INSUFFICIENT_CONTEXT_ANSWER,
                sources=[],
            )

        stage = "citation_validation"
        validation = validate_answer_citations(
            answer,
            context.sources,
        )

        # Do not expose answers with missing or invalid citations.
        if not validation.is_valid:
            obs.record_request(
                correlation_id=cid,
                mode=retrieval_mode,
                stream=False,
                rerank_opt_in=enable_reranking,
                rerank_used=rerank_used,
                rerank_fallback_reason=rerank_fallback,
                status="success",
                retrieval_ms=retrieval_ms,
                rerank_ms=rerank_ms,
                context_assembly_ms=context_ms,
                llm_generation_ms=llm_ms,
                total_ms=elapsed_ms(t_total_start),
                source_count=0,
            )
            return RAGResult(
                answer=(
                    "Không thể xác minh câu trả lời "
                    "từ tài liệu được truy xuất."
                ),
                sources=[],
            )

        obs.record_request(
            correlation_id=cid,
            mode=retrieval_mode,
            stream=False,
            rerank_opt_in=enable_reranking,
            rerank_used=rerank_used,
            rerank_fallback_reason=rerank_fallback,
            status="success",
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            context_assembly_ms=context_ms,
            llm_generation_ms=llm_ms,
            total_ms=elapsed_ms(t_total_start),
            source_count=len(context.sources),
        )
        return RAGResult(
            answer=answer,
            sources=context.sources,
        )
    except asyncio.CancelledError:
        obs.record_request(
            correlation_id=cid,
            mode=retrieval_mode,
            stream=False,
            rerank_opt_in=enable_reranking,
            rerank_used=rerank_used,
            rerank_fallback_reason=rerank_fallback,
            status="cancelled",
            failure_stage=stage,
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            context_assembly_ms=context_ms,
            llm_generation_ms=llm_ms,
            total_ms=elapsed_ms(t_total_start),
        )
        raise
    except Exception:
        obs.record_request(
            correlation_id=cid,
            mode=retrieval_mode,
            stream=False,
            rerank_opt_in=enable_reranking,
            rerank_used=rerank_used,
            rerank_fallback_reason=rerank_fallback,
            status="error",
            failure_stage=stage,
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            context_assembly_ms=context_ms,
            llm_generation_ms=llm_ms,
            total_ms=elapsed_ms(t_total_start),
        )
        raise