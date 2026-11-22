"""Request-local model routing shared by streaming and non-streaming RAG (T260040).

The LLM provider injected into the API is a process-wide singleton. Routing therefore
returns a *new* provider bound to the selected model instead of mutating the shared one,
so concurrent requests from different users, workspaces or conversations cannot change
each other's generation model.
"""

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMProvider, bind_model
from app.services.context_builder import RetrievalContext
from app.services.model_router import ModelRouter, RoutingDecisionResult
from app.services.task_classifier import TaskClassifier

logger = logging.getLogger(__name__)

# Routing is advisory: on these failures generation continues with the provider's
# configured default model, which every policy allows.
_NON_FATAL_ROUTING_ERRORS = (RuntimeError, ValueError, KeyError, OSError, AttributeError, TypeError)


@dataclass(frozen=True, slots=True)
class RoutedGeneration:
    llm: LLMProvider
    model_name: str
    routing: RoutingDecisionResult | None


def provider_model_name(llm: LLMProvider) -> str:
    return str(getattr(llm, "model", None) or "default")


async def route_rag_generation(
    session: AsyncSession | None,
    *,
    llm: LLMProvider,
    query: str,
    context: RetrievalContext,
    workspace_id: UUID | None,
) -> RoutedGeneration:
    """Select the model for this request and return a provider bound to it."""
    default = RoutedGeneration(llm=llm, model_name=provider_model_name(llm), routing=None)
    if session is None:
        return default

    has_ctx = bool(context.sources and context.text.strip())
    task_type = TaskClassifier().classify(
        prompt=query,
        has_retrieved_context=has_ctx,
        context_document_count=len(context.sources),
    )
    context_metadata: dict[str, Any] = {"query": query[:100], "source_count": len(context.sources)}
    try:
        routing = await ModelRouter().select_model(
            session=session,
            task_type=task_type,
            workspace_id=workspace_id,
            context_metadata=context_metadata,
        )
    except _NON_FATAL_ROUTING_ERRORS as exc:
        logger.warning("RAG model routing non-fatal warning: %s", exc)
        return default

    return RoutedGeneration(
        llm=bind_model(llm, routing.selected_model),
        model_name=routing.selected_model,
        routing=routing,
    )
