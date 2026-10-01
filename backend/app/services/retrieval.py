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
    user_id: UUID,
    query: str,
    limit: int = 5,
) -> RetrievalContext:
    results = await semantic_search(
        session,
        user_id=user_id,
        query=query,
        limit=limit,
    )

    return build_retrieval_context(results)