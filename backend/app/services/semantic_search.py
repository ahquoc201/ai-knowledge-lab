from dataclasses import dataclass
from uuid import UUID

from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk import search_similar_chunks
from app.services.embedding import get_embedding_service


@dataclass(frozen=True, slots=True)
class SemanticSearchResult:
    chunk: DocumentChunk
    similarity: float


def _embed_query(text: str) -> list[float]:
    service = get_embedding_service()
    return service.embed_query(text)


async def semantic_search(
    session: AsyncSession,
    *,
    user_id: UUID,
    query: str,
    limit: int = 5,
) -> list[SemanticSearchResult]:
    query_embedding = await to_thread.run_sync(
        _embed_query,
        query,
    )

    matches = await search_similar_chunks(
        session,
        user_id=user_id,
        query_embedding=query_embedding,
        limit=limit,
    )

    return [
        SemanticSearchResult(
            chunk=chunk,
            similarity=1.0 - distance,
        )
        for chunk, distance in matches
    ]