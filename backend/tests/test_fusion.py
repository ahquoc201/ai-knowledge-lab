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

    with pytest.raises(ValueError, match="Fusion weights must be non-negative"):
        reciprocal_rank_fusion([], [], dense_weight=-0.1)

    with pytest.raises(ValueError, match="Fusion weights must be non-negative"):
        reciprocal_rank_fusion([], [], keyword_weight=-0.5)


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

    # Test with default weights (dense_weight=1.0, keyword_weight=0.4):
    # c1 score: 1.0/(60+1) + 0.4/(60+2) = 1/61 + 0.4/62 = 0.0163934 + 0.0064516 = 0.022845
    # c2 score: 1.0/(60+2) + 0.4/(60+1) = 1/62 + 0.4/61 = 0.0161290 + 0.0065574 = 0.022686
    # c1 has higher weighted score -> c1 ranks first!
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
    assert r1.rrf_score == round(1.0 / 61 + 0.4 / 62, 6)

    assert r2.dense_rank == 2
    assert r2.keyword_rank == 1
    assert r2.provenance == RetrievalBranch.HYBRID
    assert r2.rrf_score == round(1.0 / 62 + 0.4 / 61, 6)

    # Test with unweighted (1.0, 1.0) where scores are equal and tie-broken by dense_rank:
    unweighted = reciprocal_rank_fusion(
        dense, keyword, k=60, dense_weight=1.0, keyword_weight=1.0, limit=2
    )
    assert unweighted[0].chunk.id == c1.id
    assert unweighted[0].rrf_score == round(1 / 61 + 1 / 62, 6)
    assert unweighted[1].rrf_score == round(1 / 61 + 1 / 62, 6)


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

    # With unweighted (1.0, 1.0):
    # c_both: 1/61 + 1/62 = 0.032522
    # c_kw_only: 1/61 = 0.016393
    # c_dense_only: 1/62 = 0.016129
    res_unweighted = reciprocal_rank_fusion(
        dense, keyword, k=60, dense_weight=1.0, keyword_weight=1.0, limit=5
    )
    assert res_unweighted[0].chunk.id == c_both.id
    assert res_unweighted[1].chunk.id == c_kw_only.id
    assert res_unweighted[2].chunk.id == c_dense_only.id

    # With default dense-biased weights (1.0, 0.4):
    # c_both: 1.0/61 + 0.4/62 = 0.022845
    # c_dense_only: 1.0/62 = 0.016129
    # c_kw_only: 0.4/61 = 0.006557
    # Dense rank 2 legitimately beats keyword rank 1, preventing spurious keyword displacement
    res_weighted = reciprocal_rank_fusion(dense, keyword, k=60, limit=5)
    assert res_weighted[0].chunk.id == c_both.id
    assert res_weighted[0].provenance == RetrievalBranch.HYBRID

    assert res_weighted[1].chunk.id == c_dense_only.id
    assert res_weighted[1].provenance == RetrievalBranch.DENSE
    assert res_weighted[1].dense_rank == 2
    assert res_weighted[1].keyword_rank is None
    assert res_weighted[1].dense_similarity == 0.85

    assert res_weighted[2].chunk.id == c_kw_only.id
    assert res_weighted[2].provenance == RetrievalBranch.KEYWORD
    assert res_weighted[2].dense_rank is None
    assert res_weighted[2].keyword_rank == 1
    assert res_weighted[2].dense_similarity is None
    assert res_weighted[2].similarity == 0.0


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


def test_weighted_rrf_dense_bias_prevents_displacement():
    # Dense rank 1 result without keyword match (e.g. cross-lingual query)
    c_dense_top = make_chunk(uuid4(), "Dense Top Match")
    # Irrelevant document with incidental keyword match (rank 1 keyword)
    c_noisy_kw = make_chunk(uuid4(), "Noisy Keyword Match")

    dense = [
        SemanticSearchResult(chunk=c_dense_top, similarity=0.88, document_title="True Doc"),
    ]
    keyword = [
        (c_noisy_kw, 0.95, "Irrelevant Long Doc"),
    ]

    # Under unweighted RRF (1.0, 1.0): both have score 1/61 = 0.016393
    # Under dense-biased RRF (1.0, 0.4):
    # c_dense_top score: 1.0 / 61 = 0.016393
    # c_noisy_kw score: 0.4 / 61 = 0.006557
    res = reciprocal_rank_fusion(dense, keyword, k=60, dense_weight=1.0, keyword_weight=0.4, limit=2)
    assert res[0].chunk.id == c_dense_top.id
    assert res[0].rrf_score > res[1].rrf_score
    assert res[0].provenance == RetrievalBranch.DENSE
    assert res[1].chunk.id == c_noisy_kw.id


def test_weighted_rrf_exact_keyword_boost():
    # An exact identifier match appears in keyword search (rank 1)
    # and also in dense search (rank 3)
    c_exact = make_chunk(uuid4(), "ERR_AUTH_001 exact error code")
    c_dense_1 = make_chunk(uuid4(), "Generic Auth Chunk 1")
    c_dense_2 = make_chunk(uuid4(), "Generic Auth Chunk 2")

    dense = [
        SemanticSearchResult(chunk=c_dense_1, similarity=0.92, document_title="Doc 1"),
        SemanticSearchResult(chunk=c_dense_2, similarity=0.90, document_title="Doc 2"),
        SemanticSearchResult(chunk=c_exact, similarity=0.85, document_title="Doc Error"),
    ]
    keyword = [
        (c_exact, 1.0, "Doc Error"),
    ]

    # c_dense_1: 1.0 / 61 = 0.016393
    # c_dense_2: 1.0 / 62 = 0.016129
    # c_exact: 1.0 / 63 + 0.4 / 61 = 0.015873 + 0.006557 = 0.022430 -> BOOSTED TO RANK 1!
    res = reciprocal_rank_fusion(dense, keyword, k=60, dense_weight=1.0, keyword_weight=0.4, limit=3)
    assert res[0].chunk.id == c_exact.id
    assert res[0].provenance == RetrievalBranch.HYBRID
    assert res[0].rrf_score == round(1.0 / 63 + 0.4 / 61, 6)

