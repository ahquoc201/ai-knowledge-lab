"""Real PostgreSQL Hybrid (pgvector + FTS + RRF) corpus retriever adapter (T260032).

Executes the production hybrid retrieval path:
- Stage 1: Query embedding (EmbeddingService)
- Stage 2: Dense pgvector cosine search (search_similar_chunks)
- Stage 3: Keyword full-text search (search_keyword_chunks)
- Stage 4: Reciprocal Rank Fusion (reciprocal_rank_fusion)
- Captures granular sub-stage latencies (embedding, vector, keyword, fusion).
"""

import time
from uuid import UUID

from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.evaluation.real_fixture_provisioner import ProvisionedRAGEnvironment
from app.repositories.document_chunk import (
    search_keyword_chunks,
    search_similar_chunks,
)
from app.services.embedding import get_embedding_service
from app.services.fusion import (
    DEFAULT_DENSE_WEIGHT,
    DEFAULT_KEYWORD_WEIGHT,
    DEFAULT_RRF_K,
    FusedSearchResult,
    reciprocal_rank_fusion,
)
from app.services.semantic_search import SemanticSearchResult


class RealHybridCorpusRetriever:
    """Production hybrid retrieval adapter implementing the CorpusRetriever protocol."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        env: ProvisionedRAGEnvironment,
        rrf_k: int = DEFAULT_RRF_K,
        dense_weight: float = DEFAULT_DENSE_WEIGHT,
        keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
        candidate_multiplier: int = 4,
    ) -> None:
        self._session_factory = session_factory
        self._env = env
        self._embedding_service = get_embedding_service()
        self._rrf_k = rrf_k
        self._dense_weight = dense_weight
        self._keyword_weight = keyword_weight
        self._candidate_multiplier = candidate_multiplier

        # Sub-stage latency tracking
        self.last_embedding_latency_ms: float = 0.0
        self.last_vector_latency_ms: float = 0.0
        self.last_keyword_latency_ms: float = 0.0
        self.last_fusion_latency_ms: float = 0.0
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
    ) -> list[FusedSearchResult]:
        """Execute hybrid search combining pgvector dense search and keyword FTS via RRF."""
        workspace_id = self._env.workspace_map.get(workspace_ref)
        if workspace_id is None:
            raise ValueError(
                f"Unknown workspace reference '{workspace_ref}'. "
                f"Available workspaces: {list(self._env.workspace_map.keys())}"
            )

        fetch_limit = max(20, limit * self._candidate_multiplier)

        # Stage 1: Query embedding
        t0_embed = time.perf_counter()
        query_embedding = await to_thread.run_sync(
            self._embedding_service.embed_query,
            query,
        )
        self.last_embedding_latency_ms = (time.perf_counter() - t0_embed) * 1000.0

        async with self._session_factory() as session:
            # Stage 2: Pgvector search
            t0_vec = time.perf_counter()
            dense_matches = await search_similar_chunks(
                session,
                workspace_id=workspace_id,
                query_embedding=query_embedding,
                limit=fetch_limit,
            )
            self.last_vector_latency_ms = (time.perf_counter() - t0_vec) * 1000.0

            dense_results = [
                SemanticSearchResult(
                    chunk=item[0],
                    similarity=1.0 - item[1],
                    document_title=item[2] if len(item) > 2 else None,
                )
                for item in dense_matches
            ]

            # Stage 3: Keyword search
            t0_kw = time.perf_counter()
            keyword_matches = await search_keyword_chunks(
                session,
                workspace_id=workspace_id,
                query=query,
                limit=fetch_limit,
            )
            self.last_keyword_latency_ms = (time.perf_counter() - t0_kw) * 1000.0

        # Stage 4: Fusion
        t0_fuse = time.perf_counter()
        fused = reciprocal_rank_fusion(
            dense_results=dense_results,
            keyword_results=keyword_matches,
            k=self._rrf_k,
            dense_weight=self._dense_weight,
            keyword_weight=self._keyword_weight,
            limit=limit,
        )
        self.last_fusion_latency_ms = (time.perf_counter() - t0_fuse) * 1000.0
        self.last_candidates_count = len(fused)

        return fused
