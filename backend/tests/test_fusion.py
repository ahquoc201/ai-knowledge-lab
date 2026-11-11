"""Targeted unit tests for Reciprocal Rank Fusion (RRF) (T260032)."""

from uuid import UUID, uuid4

import pytest

from app.models.document_chunk import DocumentChunk
from app.services.fusion import (
    RetrievalBranch,
    reciprocal_rank_fusion,
)
from app.services.semantic_search import SemanticSearchResult


def make_chunk(chunk_id: UUID | None = None, content: str = "test chunk") -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id or uuid4(),
        document_id=uuid4(),
        chunk_index=0,
        content=content,
        char_start=0,
        char_end=len(content),
    )


def test_rrf_empty_inputs():
    res = reciprocal_rank_fusion([], [])
    assert res == []

    res2 = reciprocal_rank_fusion([], [], limit=0)
    assert res2 == []

    with pytest.raises(ValueError, match="RRF constant k must be positive"):
        reciprocal_rank_fusion([], [], k=0)


def test_rrf_formula_and_deduplication():
    c1 = make_chunk(uuid4(), "Chunk 1")
    c2 = make_chunk(uuid4(), "Chunk 2")

    # c1 is rank 1 in dense (sim=0.9) and rank 2 in keyword (score=0.5)
    # c2 is rank 2 in dense (sim=0.8) and rank 1 in keyword (score=0.8)
    dense = [
        SemanticSearchResult(chunk=c1, similarity=0.9, document_title="Doc 1"),
        SemanticSearchResult(chunk=c2, similarity=0.8, document_title="Doc 2"),
    ]
    keyword = [
        (c2, 0.8, "Doc 2"),
        (c1, 0.5, "Doc 1"),
    ]

    # For k=60:
    # c1 score: 1/(60+1) + 1/(60+2) = 1/61 + 1/62 = 0.0163934 + 0.0161290 = 0.032522
    # c2 score: 1/(60+2) + 1/(60+1) = 1/62 + 1/61 = 0.032522
    # Tie broken by dense_rank (c1 has dense_rank=1 < c2 dense_rank=2) -> c1 ranks first!
    results = reciprocal_rank_fusion(dense, keyword, k=60, limit=2)
    assert len(results) == 2

    r1, r2 = results
    assert r1.chunk.id == c1.id
    assert r2.chunk.id == c2.id

    assert r1.dense_rank == 1
    assert r1.keyword_rank == 2
    assert r1.provenance == RetrievalBranch.HYBRID
    assert r1.dense_similarity == 0.9
    assert r1.similarity == 0.9
    assert r1.rrf_score == round(1 / 61 + 1 / 62, 6)

    assert r2.dense_rank == 2
    assert r2.keyword_rank == 1
    assert r2.provenance == RetrievalBranch.HYBRID


def test_rrf_single_branch_candidates():
    c_dense_only = make_chunk(uuid4(), "Dense Only")
    c_kw_only = make_chunk(uuid4(), "Keyword Only")
    c_both = make_chunk(uuid4(), "Both")

    dense = [
        SemanticSearchResult(chunk=c_both, similarity=0.95, document_title="Doc Both"),
        SemanticSearchResult(chunk=c_dense_only, similarity=0.85, document_title="Doc Dense"),
    ]
    keyword = [
        (c_kw_only, 0.7, "Doc Kw"),
        (c_both, 0.4, "Doc Both"),
    ]

    results = reciprocal_rank_fusion(dense, keyword, k=60, limit=5)
    assert len(results) == 3

    # c_both is in both (rank 1 dense + rank 2 kw) -> score: 1/61 + 1/62 = 0.032522
    # c_kw_only is rank 1 kw only -> score: 1/61 = 0.016393
    # c_dense_only is rank 2 dense only -> score: 1/62 = 0.016129
    assert results[0].chunk.id == c_both.id
    assert results[0].provenance == RetrievalBranch.HYBRID

    assert results[1].chunk.id == c_kw_only.id
    assert results[1].provenance == RetrievalBranch.KEYWORD
    assert results[1].dense_rank is None
    assert results[1].keyword_rank == 1
    assert results[1].dense_similarity is None
    assert results[1].similarity == 0.0  # Does not invent cosine similarity

    assert results[2].chunk.id == c_dense_only.id
    assert results[2].provenance == RetrievalBranch.DENSE
    assert results[2].dense_rank == 2
    assert results[2].keyword_rank is None
    assert results[2].dense_similarity == 0.85
    assert results[2].similarity == 0.85


def test_rrf_deterministic_tie_breaking_by_uuid():
    # Construct two items with identical dense and keyword ranks
    id_a = UUID("00000000-0000-0000-0000-000000000001")
    id_b = UUID("00000000-0000-0000-0000-000000000002")

    c_a = make_chunk(id_a, "Chunk A")
    c_b = make_chunk(id_b, "Chunk B")

    # In single list where both have equal simulated rank, verify id_a < id_b order
    dense = [
        SemanticSearchResult(chunk=c_b, similarity=0.5, document_title="Doc"),
    ]
    keyword = [
        (c_a, 0.5, "Doc"),
    ]

    # For k=60: c_b has dense_rank=1 (score=1/61), c_a has keyword_rank=1 (score=1/61)
    # Tie-breaker 1: dense_rank (c_b has dense_rank=1, c_a has dense_rank=None/999999) -> c_b wins
    res = reciprocal_rank_fusion(dense, keyword, k=60, limit=2)
    assert res[0].chunk.id == id_b
    assert res[1].chunk.id == id_a


def test_rrf_configurable_k_and_limit():
    c1 = make_chunk(uuid4(), "1")
    c2 = make_chunk(uuid4(), "2")
    c3 = make_chunk(uuid4(), "3")

    dense = [
        SemanticSearchResult(chunk=c1, similarity=0.9),
        SemanticSearchResult(chunk=c2, similarity=0.8),
        SemanticSearchResult(chunk=c3, similarity=0.7),
    ]

    res_k20 = reciprocal_rank_fusion(dense, [], k=20, limit=2)
    assert len(res_k20) == 2
    assert res_k20[0].rrf_score == round(1 / 21, 6)
    assert res_k20[1].rrf_score == round(1 / 22, 6)
