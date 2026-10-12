
"""Adapters connecting retrieval engines to evaluation."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.semantic_search import semantic_search


class SemanticSearchRetriever:
    """Adapt semantic search to the evaluation retriever contract."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
    ) -> None:
        self._session = session
        self._user_id = user_id

    async def __call__(
        self,
        query: str,
        limit: int,
    ) -> list[UUID]:
        """Return chunk IDs in semantic relevance order."""

        matches = await semantic_search(
            self._session,
            user_id=self._user_id,
            query=query,
            limit=limit,
        )

        return [
            match.chunk.id
            for match in matches
        ]
