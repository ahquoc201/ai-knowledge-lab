"""Real PostgreSQL pgvector corpus retriever adapter for RAG evaluation (T260031).

Invokes the actual production retrieval execution path:
Query -> EmbeddingService.embed_query -> search_similar_chunks (PostgreSQL pgvector cosine_distance)
-> Workspace tenant isolation -> SemanticSearchResult.
"""

import time
from uuid import UUID

from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.evaluation.real_fixture_provisioner import ProvisionedRAGEnvironment
from app.repositories.document_chunk import search_similar_chunks
from app.services.embedding import get_embedding_service
from app.services.semantic_search import SemanticSearchResult


class RealPgVectorCorpusRetriever:
    """Production pgvector retrieval adapter implementing the CorpusRetriever protocol.

    Executes live SQL queries with pgvector cosine similarity and captures granular
    sub-stage latencies (query embedding vs vector query).
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        env: ProvisionedRAGEnvironment,
    ) -> None:
        self._session_factory = session_factory
        self._env = env
        self._embedding_service = get_embedding_service()

        # Last execution sub-stage diagnostic traces
        self.last_embedding_latency_ms: float = 0.0
        self.last_vector_latency_ms: float = 0.0
        self.last_candidates_count: int = 0

    def get_document_key_for_chunk(self, chunk_id: UUID) -> str | None:
        """Resolve database chunk UUID to the canonical synthetic fixture document key."""
        return self._env.chunk_doc_map.get(chunk_id)

    def get_workspace_ref_for_chunk(self, chunk_id: UUID) -> str | None:
        """Resolve database chunk UUID to the fixture workspace reference."""
        return self._env.chunk_ws_map.get(chunk_id)

    def get_document_chunks(self, document_key: str) -> list[UUID]:
        """Return all chunk UUIDs belonging to a fixture document key."""
        return self._env.document_chunks_by_key.get(document_key, [])

    async def search(
        self,
        query: str,
        workspace_ref: str,
        limit: int,
    ) -> list[SemanticSearchResult]:
        """Execute real query embedding and pgvector cosine search through production repository."""
        workspace_id = self._env.workspace_map.get(workspace_ref)
        if workspace_id is None:
            raise ValueError(
                f"Unknown workspace reference '{workspace_ref}'. "
                f"Available workspaces: {list(self._env.workspace_map.keys())}"
            )

        # Stage 1: Query embedding
        t0_embed = time.perf_counter()
        query_embedding = await to_thread.run_sync(
            self._embedding_service.embed_query,
            query,
        )
        self.last_embedding_latency_ms = (time.perf_counter() - t0_embed) * 1000.0

        # Stage 2: Live pgvector search in PostgreSQL
        t0_vec = time.perf_counter()
        async with self._session_factory() as session:
            matches = await search_similar_chunks(
                session,
                workspace_id=workspace_id,
                query_embedding=query_embedding,
                limit=limit,
            )
        self.last_vector_latency_ms = (time.perf_counter() - t0_vec) * 1000.0
        self.last_candidates_count = len(matches)

        # Convert to production SemanticSearchResult dataclass
        return [
            SemanticSearchResult(
                chunk=item[0],
                similarity=1.0 - item[1],
                document_title=item[2] if len(item) > 2 else None,
            )
            for item in matches
        ]
