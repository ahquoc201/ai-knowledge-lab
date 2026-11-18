import inspect
from enum import Enum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.document_chunk import search_keyword_chunks
from app.services.context_builder import (
    RetrievalContext,
    build_retrieval_context,
)
from app.services.fusion import (
    DEFAULT_DENSE_WEIGHT,
    DEFAULT_KEYWORD_WEIGHT,
    DEFAULT_RRF_K,
    FusedSearchResult,
    reciprocal_rank_fusion,
)
from app.services.reranker import get_reranker_service
from app.services.semantic_search import SemanticSearchResult, semantic_search


class RetrievalMode(str, Enum):
    DENSE = "dense"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


async def hybrid_search(
    session: AsyncSession,
    *,
    user_id: UUID | None = None,
    workspace_id: UUID | None = None,
    query: str,
    limit: int = 5,
    rrf_k: int = DEFAULT_RRF_K,
    dense_weight: float = DEFAULT_DENSE_WEIGHT,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    candidate_multiplier: int = 4,
) -> list[FusedSearchResult]:
    """Execute hybrid retrieval combining dense semantic search and keyword FTS via RRF.

    Fetches up to max(20, limit * candidate_multiplier) candidates from both branches
    safely on the current session, then fuses rankings deterministically.
    """
    if workspace_id is None and user_id is None:
        raise ValueError("Either workspace_id or user_id must be provided")

    fetch_limit = max(20, limit * candidate_multiplier)

    # 1. Dense search branch
    dense_results = await semantic_search(
        session,
        user_id=user_id,
        workspace_id=workspace_id,
        query=query,
        limit=fetch_limit,
    )

    # 2. Keyword FTS branch
    keyword_results = await search_keyword_chunks(
        session,
        user_id=user_id,
        workspace_id=workspace_id,
        query=query,
        limit=fetch_limit,
    )

    # 3. Reciprocal Rank Fusion
    return reciprocal_rank_fusion(
        dense_results=dense_results,
        keyword_results=keyword_results,
        k=rrf_k,
        dense_weight=dense_weight,
        keyword_weight=keyword_weight,
        limit=limit,
    )


async def retrieve_candidates(
    session: AsyncSession,
    *,
    user_id: UUID | None = None,
    workspace_id: UUID | None = None,
    query: str,
    limit: int = 5,
    mode: str | RetrievalMode = RetrievalMode.DENSE,
    rrf_k: int = DEFAULT_RRF_K,
    dense_weight: float = DEFAULT_DENSE_WEIGHT,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
) -> list[SemanticSearchResult | FusedSearchResult]:
    """Retrieve raw candidate chunks based on the configured retrieval mode."""
    norm_mode = str(getattr(mode, "value", mode)).lower()

    if norm_mode in (RetrievalMode.HYBRID.value, "hybrid"):
        return await hybrid_search(
            session,
            user_id=user_id,
            workspace_id=workspace_id,
            query=query,
            limit=limit,
            rrf_k=rrf_k,
            dense_weight=dense_weight,
            keyword_weight=keyword_weight,
        )
    elif norm_mode in (RetrievalMode.KEYWORD.value, "keyword"):
        keyword_raw = await search_keyword_chunks(
            session,
            user_id=user_id,
            workspace_id=workspace_id,
            query=query,
            limit=limit,
        )
        return reciprocal_rank_fusion(
            dense_results=[],
            keyword_results=keyword_raw,
            k=rrf_k,
            dense_weight=dense_weight,
            keyword_weight=keyword_weight,
            limit=limit,
        )
    else:
        # Default dense search behavior
        search_kwargs = {
            "session": session,
            "query": query,
            "limit": limit,
        }
        if user_id is not None:
            search_kwargs["user_id"] = user_id

        if workspace_id is not None and "workspace_id" in inspect.signature(semantic_search).parameters:
            search_kwargs["workspace_id"] = workspace_id

        return await semantic_search(**search_kwargs)


async def retrieve_context(
    session: AsyncSession,
    *,
    user_id: UUID | None = None,
    workspace_id: UUID | None = None,
    query: str,
    limit: int = 5,
    mode: str | RetrievalMode = RetrievalMode.DENSE,
    rrf_k: int = DEFAULT_RRF_K,
    dense_weight: float = DEFAULT_DENSE_WEIGHT,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    enable_reranking: bool = False,
) -> RetrievalContext:
    """Retrieve context bounded by character budget, with configurable retrieval mode and opt-in reranking.

    Default mode is strictly DENSE and reranking is disabled by default to preserve backward compatibility.
    """
    settings = get_settings()

    # Determine candidate pool size: expand if client opted-in and server has reranker enabled
    fetch_limit = limit
    if enable_reranking and settings.reranker_enabled:
        fetch_limit = max(limit, settings.reranker_pool_size)

    candidates = await retrieve_candidates(
        session,
        user_id=user_id,
        workspace_id=workspace_id,
        query=query,
        limit=fetch_limit,
        mode=mode,
        rrf_k=rrf_k,
        dense_weight=dense_weight,
        keyword_weight=keyword_weight,
    )

    if enable_reranking:
        reranker_service = get_reranker_service()
        final_results, _is_reranked, _fallback = await reranker_service.rerank_candidates(
            query=query,
            candidates=candidates,
            limit=limit,
            opt_in=True,
        )
        return build_retrieval_context(final_results)

    return build_retrieval_context(candidates[:limit])
