"""Reciprocal Rank Fusion (RRF) for Hybrid Retrieval (T260032).

Implements a pure, deterministic fusion algorithm combining Dense Vector Search
and Keyword Full-Text Search rankings.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from app.models.document_chunk import DocumentChunk
from app.services.semantic_search import SemanticSearchResult

DEFAULT_RRF_K = 60
DEFAULT_DENSE_WEIGHT = 1.0
DEFAULT_KEYWORD_WEIGHT = 0.4


class RetrievalBranch(str, Enum):
    DENSE = "dense"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class FusedSearchResult:
    """Represents a retrieval candidate ranked by Reciprocal Rank Fusion (RRF).

    Fields:
    - chunk: DocumentChunk ORM object.
    - rrf_score: Fused score calculated as sum(1 / (k + rank)).
    - dense_rank: 1-based rank in dense search (None if not in dense candidates).
    - keyword_rank: 1-based rank in keyword search (None if not in keyword candidates).
    - dense_similarity: Cosine similarity score from dense search (None if absent).
    - keyword_score: PostgreSQL ts_rank score from keyword search (None if absent).
    - document_title: Title of parent document.
    """

    chunk: DocumentChunk
    rrf_score: float
    dense_rank: int | None = None
    keyword_rank: int | None = None
    dense_similarity: float | None = None
    keyword_score: float | None = None
    document_title: str | None = None

    @property
    def provenance(self) -> RetrievalBranch:
        if self.dense_rank is not None and self.keyword_rank is not None:
            return RetrievalBranch.HYBRID
        elif self.dense_rank is not None:
            return RetrievalBranch.DENSE
        else:
            return RetrievalBranch.KEYWORD

    @property
    def similarity(self) -> float:
        """Preserves true cosine similarity for downstream context budgeting.

        Never misrepresents RRF score as cosine similarity.
        """
        return self.dense_similarity if self.dense_similarity is not None else 0.0


def reciprocal_rank_fusion(
    dense_results: Sequence[SemanticSearchResult | tuple[DocumentChunk, float, str]],
    keyword_results: Sequence[tuple[DocumentChunk, float, str]],
    *,
    k: int = DEFAULT_RRF_K,
    dense_weight: float = DEFAULT_DENSE_WEIGHT,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    limit: int = 5,
) -> list[FusedSearchResult]:
    """Fuse dense and keyword search candidate lists using Reciprocal Rank Fusion (RRF).

    Formula:
        RRF_Score(d) = (dense_weight / (k + rank_dense(d))) + (keyword_weight / (k + rank_keyword(d)))

    Tie-breaking:
        1. rrf_score (descending)
        2. dense_rank (ascending; lower rank is better, absent = infinity)
        3. keyword_rank (ascending; lower rank is better, absent = infinity)
        4. chunk.id (ascending UUID string for 100% determinism)
    """
    if k <= 0:
        raise ValueError("RRF constant k must be positive")
    if dense_weight < 0 or keyword_weight < 0:
        raise ValueError("Fusion weights must be non-negative")
    if limit <= 0:
        return []

    candidates: dict[UUID, dict] = {}

    # 1. Process dense candidates
    for rank, item in enumerate(dense_results, start=1):
        if isinstance(item, SemanticSearchResult):
            chunk = item.chunk
            similarity = float(item.similarity)
            title = item.document_title
        else:
            chunk = item[0]
            similarity = float(item[1])
            title = str(item[2]) if len(item) > 2 else None

        chunk_id = chunk.id
        if chunk_id not in candidates:
            candidates[chunk_id] = {
                "chunk": chunk,
                "document_title": title,
                "dense_rank": rank,
                "dense_similarity": similarity,
                "keyword_rank": None,
                "keyword_score": None,
            }
        else:
            # First occurrence in ranked list takes precedence
            if candidates[chunk_id]["dense_rank"] is None:
                candidates[chunk_id]["dense_rank"] = rank
                candidates[chunk_id]["dense_similarity"] = similarity

    # 2. Process keyword candidates
    for rank, item in enumerate(keyword_results, start=1):
        chunk = item[0]
        score = float(item[1])
        title = str(item[2]) if len(item) > 2 else None

        chunk_id = chunk.id
        if chunk_id not in candidates:
            candidates[chunk_id] = {
                "chunk": chunk,
                "document_title": title,
                "dense_rank": None,
                "dense_similarity": None,
                "keyword_rank": rank,
                "keyword_score": score,
            }
        else:
            if candidates[chunk_id]["keyword_rank"] is None:
                candidates[chunk_id]["keyword_rank"] = rank
                candidates[chunk_id]["keyword_score"] = score
            if candidates[chunk_id]["document_title"] is None and title is not None:
                candidates[chunk_id]["document_title"] = title

    # 3. Compute RRF scores
    fused: list[FusedSearchResult] = []
    for data in candidates.values():
        score = 0.0
        if data["dense_rank"] is not None:
            score += dense_weight / (k + data["dense_rank"])
        if data["keyword_rank"] is not None:
            score += keyword_weight / (k + data["keyword_rank"])

        fused.append(
            FusedSearchResult(
                chunk=data["chunk"],
                rrf_score=round(score, 6),
                dense_rank=data["dense_rank"],
                keyword_rank=data["keyword_rank"],
                dense_similarity=data["dense_similarity"],
                keyword_score=data["keyword_score"],
                document_title=data["document_title"],
            )
        )

    # 4. Deterministic sorting
    fused.sort(
        key=lambda r: (
            -r.rrf_score,
            r.dense_rank if r.dense_rank is not None else 999_999,
            r.keyword_rank if r.keyword_rank is not None else 999_999,
            str(r.chunk.id),
        )
    )

    return fused[:limit]
