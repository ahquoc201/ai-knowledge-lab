"""Streaming RAG pipeline with lifecycle events, citation validation, and persistence."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.message_role import MessageRole
from app.llm.base import LLMMessage, LLMProvider
from app.models.user import User
from app.services.citation_validation import validate_answer_citations
from app.services.context_builder import ContextSource
from app.services.inference_governor import get_inference_governor
from app.services.message import (
    create_conversation_message,
    create_workspace_conversation_message,
)
from app.services.message_source import save_assistant_message_sources
from app.services.rag_observability import (
    elapsed_ms,
    get_rag_observability,
    sanitize_correlation_id,
)
from app.services.rag_prompt import (
    INSUFFICIENT_CONTEXT_ANSWER,
    build_rag_messages,
)
from app.services.rag_routing import route_rag_generation
from app.services.retrieval import retrieve_context

logger = logging.getLogger(__name__)

UNVERIFIED_CITATION_ANSWER = "Không thể xác minh câu trả lời từ tài liệu được truy xuất."
LLM_UNAVAILABLE_MESSAGE = (
    "Mô hình ngôn ngữ hiện không khả dụng hoặc phản hồi quá chậm. "
    "Vui lòng thử lại sau."
)
RAG_INTERNAL_ERROR_MESSAGE = "Đã xảy ra lỗi khi xử lý câu hỏi. Vui lòng thử lại sau."


def describe_stream_failure(exc: Exception) -> tuple[str, str]:
    """Map an internal failure to a stable error code and a user-facing message.

    Raw exception text (upstream URLs, driver errors) is never sent to clients.
    """
    if isinstance(exc, httpx.HTTPError):
        return "llm_unavailable", LLM_UNAVAILABLE_MESSAGE
    if isinstance(exc, HTTPException):
        return "service_busy", str(exc.detail)
    return "internal_error", RAG_INTERNAL_ERROR_MESSAGE


async def _persist_assistant_message(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID | None,
    conversation_id: UUID,
    content: str,
):
    """Persist the assistant reply in the same scope the API used to authorize the conversation.

    Workspace conversations may be continued by any member, so they are resolved by
    workspace rather than by the original conversation owner.
    """
    if workspace_id is not None:
        return await create_workspace_conversation_message(
            session,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=content,
        )
    return await create_conversation_message(
        session,
        user=user,
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=content,
    )


def format_sse(event_type: str, data: dict[str, Any]) -> str:
    """Format SSE chunk with both event name and typed JSON data."""
    payload = {"event": event_type, **data}
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def serialize_source(source: ContextSource) -> dict[str, Any]:
    return {
        "source_index": source.source_index,
        "document_id": str(source.document_id),
        "chunk_id": str(source.chunk_id),
        "chunk_index": source.chunk_index,
        "content": source.content,
        "similarity": source.similarity,
        "document_title": source.document_title,
        "char_start": source.char_start,
        "char_end": source.char_end,
        "rerank_score": source.rerank_score,
    }


async def answer_with_rag_stream(
    session: AsyncSession,
    *,
    user: User,
    conversation_id: UUID,
    workspace_id: UUID | None = None,
    query: str,
    llm: LLMProvider,
    limit: int = 5,
    history: list[LLMMessage] | None = None,
    retrieval_mode: str = "dense",
    enable_reranking: bool = False,
) -> AsyncIterator[str]:
    """Execute streaming RAG workflow with guardrails and persistence.

    Lifecycle:
    1. retrieval_started
    2. retrieval_completed (emits sources)
    3. generation_started (if evidence found)
    4. token (yields raw tokens as they stream from LLM)
    5. answer_completed (verifies citations; falls back to refusal if invalid, persists message)
    6. error (on unhandled exceptions)
    """
    t_total_start = time.perf_counter()
    cid = sanitize_correlation_id(str(conversation_id))
    obs = get_rag_observability()

    retrieval_ms: float | None = None
    context_ms: float | None = None
    rerank_ms: float | None = None
    rerank_used = False
    rerank_fallback: str | None = None
    llm_ms: float | None = None
    ttft_ms: float | None = None
    stage = "retrieval"

    try:
        yield format_sse(
            "retrieval_started",
            {
                "query": query,
                "conversation_id": str(conversation_id),
            },
        )

        import inspect

        retrieval_kwargs = {
            "session": session,
            "user_id": user.id,
            "query": query,
            "limit": limit,
        }
        sig_params = inspect.signature(retrieve_context).parameters
        has_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig_params.values())

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

        serialized_sources = [serialize_source(s) for s in context.sources]
        yield format_sse("retrieval_completed", {"sources": serialized_sources})

        # Adaptive model routing (request-local: never mutates the shared provider)
        stage = "model_routing"
        routed = await route_rag_generation(
            session,
            llm=llm,
            query=query,
            context=context,
            workspace_id=workspace_id,
        )
        request_llm = routed.llm
        routed_model = routed.model_name
        if routed.routing is not None:
            yield format_sse(
                "model_routed",
                {
                    "model": routed.routing.selected_model,
                    "task_type": routed.routing.task_type,
                    "reason": routed.routing.selection_reason,
                    "fallback_occurred": routed.routing.is_fallback,
                },
            )

        # Guardrail 1: Refuse when no usable evidence exists
        if not context.sources or not context.text.strip():
            ttft_ms = elapsed_ms(t_total_start)
            yield format_sse("token", {"token": INSUFFICIENT_CONTEXT_ANSWER})

            assistant_message = await _persist_assistant_message(
                session,
                user=user,
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                content=INSUFFICIENT_CONTEXT_ANSWER,
            )

            obs.record_request(
                correlation_id=cid,
                mode=retrieval_mode,
                stream=True,
                rerank_opt_in=enable_reranking,
                rerank_used=rerank_used,
                rerank_fallback_reason=rerank_fallback,
                status="success",
                retrieval_ms=retrieval_ms,
                rerank_ms=rerank_ms,
                context_assembly_ms=context_ms,
                ttft_ms=ttft_ms,
                total_ms=elapsed_ms(t_total_start),
                source_count=0,
            )

            yield format_sse(
                "answer_completed",
                {
                    "conversation_id": str(conversation_id),
                    "message_id": str(assistant_message.id) if assistant_message else None,
                    "answer": INSUFFICIENT_CONTEXT_ANSWER,
                    "sources": [],
                    "model_name": routed_model,
                },
            )
            return

        stage = "context_assembly"
        messages = build_rag_messages(
            query=query,
            context=context,
            history=history,
        )

        yield format_sse("generation_started", {"model_name": routed_model})

        stage = "llm_generation"
        accumulated_tokens: list[str] = []
        governor = get_inference_governor()
        t_llm_start = time.perf_counter()
        async with governor.acquire(caller_info=f"rag_stream:{conversation_id}"):
            async for token in request_llm.generate_stream(messages):
                if ttft_ms is None:
                    ttft_ms = elapsed_ms(t_total_start)
                accumulated_tokens.append(token)
                yield format_sse("token", {"token": token})
        llm_ms = elapsed_ms(t_llm_start)

        raw_answer = "".join(accumulated_tokens)

        # Guardrail 2: Model self-refusal
        if raw_answer.strip() == INSUFFICIENT_CONTEXT_ANSWER:
            final_answer = INSUFFICIENT_CONTEXT_ANSWER
            final_sources: list[ContextSource] = []
        else:
            # Guardrail 3: Strict citation validation
            stage = "citation_validation"
            validation = validate_answer_citations(raw_answer, context.sources)
            if not validation.is_valid:
                final_answer = UNVERIFIED_CITATION_ANSWER
                final_sources = []
            else:
                final_answer = raw_answer
                final_sources = context.sources

        # Persist assistant message and citations
        stage = "persistence"
        assistant_message = await _persist_assistant_message(
            session,
            user=user,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            content=final_answer,
        )

        if assistant_message is not None and final_sources:
            await save_assistant_message_sources(
                session,
                message=assistant_message,
                sources=final_sources,
            )

        obs.record_request(
            correlation_id=cid,
            mode=retrieval_mode,
            stream=True,
            rerank_opt_in=enable_reranking,
            rerank_used=rerank_used,
            rerank_fallback_reason=rerank_fallback,
            status="success",
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            context_assembly_ms=context_ms,
            llm_generation_ms=llm_ms,
            ttft_ms=ttft_ms,
            total_ms=elapsed_ms(t_total_start),
            source_count=len(final_sources),
        )

        yield format_sse(
            "answer_completed",
            {
                "conversation_id": str(conversation_id),
                "message_id": str(assistant_message.id) if assistant_message else None,
                "answer": final_answer,
                "sources": [serialize_source(s) for s in final_sources],
                "model_name": routed_model,
            },
        )

    except asyncio.CancelledError:
        obs.record_request(
            correlation_id=cid,
            mode=retrieval_mode,
            stream=True,
            rerank_opt_in=enable_reranking,
            rerank_used=rerank_used,
            rerank_fallback_reason=rerank_fallback,
            status="cancelled",
            failure_stage=stage,
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            context_assembly_ms=context_ms,
            llm_generation_ms=llm_ms,
            ttft_ms=ttft_ms,
            total_ms=elapsed_ms(t_total_start),
        )
        raise
    except Exception as exc:
        obs.record_request(
            correlation_id=cid,
            mode=retrieval_mode,
            stream=True,
            rerank_opt_in=enable_reranking,
            rerank_used=rerank_used,
            rerank_fallback_reason=rerank_fallback,
            status="error",
            failure_stage=stage,
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            context_assembly_ms=context_ms,
            llm_generation_ms=llm_ms,
            ttft_ms=ttft_ms,
            total_ms=elapsed_ms(t_total_start),
        )
        logger.exception(
            "RAG stream failed at stage=%s conversation=%s",
            stage,
            conversation_id,
        )
        code, message = describe_stream_failure(exc)
        yield format_sse("error", {"error": message, "code": code, "stage": stage})
