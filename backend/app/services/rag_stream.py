"""Streaming RAG pipeline with lifecycle events, citation validation, and persistence."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.message_role import MessageRole
from app.llm.base import LLMMessage, LLMProvider
from app.models.user import User
from app.services.citation_validation import validate_answer_citations
from app.services.context_builder import ContextSource
from app.services.message import create_conversation_message
from app.services.message_source import save_assistant_message_sources
from app.services.model_router import ModelRouter
from app.services.rag_prompt import (
    INSUFFICIENT_CONTEXT_ANSWER,
    build_rag_messages,
)
from app.services.retrieval import retrieve_context
from app.services.task_classifier import TaskClassifier

logger = logging.getLogger(__name__)

UNVERIFIED_CITATION_ANSWER = "Không thể xác minh câu trả lời từ tài liệu được truy xuất."


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
        if workspace_id is not None and "workspace_id" in inspect.signature(retrieve_context).parameters:
            retrieval_kwargs["workspace_id"] = workspace_id

        context = await retrieve_context(**retrieval_kwargs)

        serialized_sources = [serialize_source(s) for s in context.sources]
        yield format_sse("retrieval_completed", {"sources": serialized_sources})

        # Adaptive Model Routing
        model_router = ModelRouter()
        classifier = TaskClassifier()
        has_ctx = bool(context.sources and context.text.strip())
        task_type = classifier.classify(
            prompt=query,
            has_retrieved_context=has_ctx,
            context_document_count=len(context.sources),
        )
        routed_model = getattr(llm, "model", "default")
        if session is not None:
            try:
                routing = await model_router.select_model(
                    session=session,
                    task_type=task_type,
                    workspace_id=workspace_id,
                    context_metadata={"query": query[:100], "source_count": len(context.sources)},
                )
                routed_model = routing.selected_model
                if hasattr(llm, "model"):
                    llm.model = routed_model
                yield format_sse(
                    "model_routed",
                    {
                        "model": routing.selected_model,
                        "task_type": routing.task_type,
                        "reason": routing.selection_reason,
                        "fallback_occurred": routing.is_fallback,
                    },
                )
            except (RuntimeError, ValueError, KeyError, OSError, AttributeError) as e:
                logger.warning("RAG model routing non-fatal warning: %s", e)

        # Guardrail 1: Refuse when no usable evidence exists
        if not context.sources or not context.text.strip():
            yield format_sse("token", {"token": INSUFFICIENT_CONTEXT_ANSWER})

            assistant_message = await create_conversation_message(
                session,
                user=user,
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=INSUFFICIENT_CONTEXT_ANSWER,
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

        messages = build_rag_messages(
            query=query,
            context=context,
            history=history,
        )

        yield format_sse("generation_started", {"model_name": routed_model})

        accumulated_tokens: list[str] = []
        async for token in llm.generate_stream(messages):
            accumulated_tokens.append(token)
            yield format_sse("token", {"token": token})

        raw_answer = "".join(accumulated_tokens)

        # Guardrail 2: Model self-refusal
        if raw_answer.strip() == INSUFFICIENT_CONTEXT_ANSWER:
            final_answer = INSUFFICIENT_CONTEXT_ANSWER
            final_sources: list[ContextSource] = []
        else:
            # Guardrail 3: Strict citation validation
            validation = validate_answer_citations(raw_answer, context.sources)
            if not validation.is_valid:
                final_answer = UNVERIFIED_CITATION_ANSWER
                final_sources = []
            else:
                final_answer = raw_answer
                final_sources = context.sources

        # Persist assistant message and citations
        assistant_message = await create_conversation_message(
            session,
            user=user,
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=final_answer,
        )

        if assistant_message is not None and final_sources:
            await save_assistant_message_sources(
                session,
                message=assistant_message,
                sources=final_sources,
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

    except Exception as exc:  # noqa: BLE001
        yield format_sse("error", {"error": str(exc)})
