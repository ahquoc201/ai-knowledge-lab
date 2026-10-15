import inspect
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.context_builder import (
    RetrievalContext,
    build_retrieval_context,
)
from app.services.semantic_search import semantic_search


async def retrieve_context(
    session: AsyncSession,
    *,
    user_id: UUID | None = None,
    workspace_id: UUID | None = None,
    query: str,
    limit: int = 5,
) -> RetrievalContext:
    search_kwargs = {
        "session": session,
        "query": query,
        "limit": limit,
    }
    if user_id is not None:
        search_kwargs["user_id"] = user_id

    if workspace_id is not None and "workspace_id" in inspect.signature(semantic_search).parameters:
        search_kwargs["workspace_id"] = workspace_id

    results = await semantic_search(**search_kwargs)

    return build_retrieval_context(results)