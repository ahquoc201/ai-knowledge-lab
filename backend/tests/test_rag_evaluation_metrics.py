"""Unit tests for pure RAG retrieval metrics (T260030)."""

import pytest
from app.evaluation.rag_metrics import (
    empty_retrieval_rate,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
    retrieval_coverage,
    tenant_isolation_rate,
)


def test_precision_at_k_normal():
    retrieved = ["doc_a", "doc_b", "doc_c", "doc_d", "doc_e"]
    expected = {"doc_a", "doc_c"}
    assert precision_at_k(retrieved, expected, 5) == 2 / 5
    assert precision_at_k(retrieved, expected, 3) == 2 / 3
    assert precision_at_k(retrieved, expected, 1) == 1.0


def test_precision_at_k_empty_expected():
    retrieved = ["doc_a", "doc_b"]
    assert precision_at_k(retrieved, set(), 2) == 0.0


def test_precision_at_k_invalid_k():
    with pytest.raises(ValueError, match="positive integer"):
        precision_at_k(["a"], {"a"}, 0)
    with pytest.raises(ValueError, match="positive integer"):
        precision_at_k(["a"], {"a"}, -1)


def test_recall_at_k_normal():
    retrieved = ["doc_a", "doc_b", "doc_c", "doc_d"]
    expected = {"doc_a", "doc_x"}
    assert recall_at_k(retrieved, expected, 4) == 0.5
    assert recall_at_k(retrieved, expected, 1) == 0.5


def test_recall_at_k_empty_expected_raises():
    with pytest.raises(ValueError, match="expected_keys must not be empty"):
        recall_at_k(["a"], set(), 1)


def test_reciprocal_rank_at_k():
    retrieved = ["doc_a", "doc_b", "doc_c"]
    assert reciprocal_rank_at_k(retrieved, {"doc_a"}, 3) == 1.0
    assert reciprocal_rank_at_k(retrieved, {"doc_b"}, 3) == 0.5
    assert reciprocal_rank_at_k(retrieved, {"doc_c"}, 3) == 1 / 3
    assert reciprocal_rank_at_k(retrieved, {"doc_x"}, 3) == 0.0
    assert reciprocal_rank_at_k(retrieved, set(), 3) == 0.0


def test_mean_reciprocal_rank():
    assert mean_reciprocal_rank([1.0, 0.5, 0.0]) == 0.5
    assert mean_reciprocal_rank([]) == 0.0
    with pytest.raises(ValueError, match="Invalid reciprocal rank"):
        mean_reciprocal_rank([1.5])


def test_retrieval_coverage():
    assert retrieval_coverage([1, 2, 0, 1]) == 3 / 4
    assert retrieval_coverage([]) == 0.0
    assert retrieval_coverage([0, 0]) == 0.0


def test_empty_retrieval_rate():
    assert empty_retrieval_rate([5, 0, 3, 0]) == 0.5
    assert empty_retrieval_rate([]) == 0.0
    assert empty_retrieval_rate([1, 2, 3]) == 0.0


def test_tenant_isolation_rate():
    assert tenant_isolation_rate([0, 0, 1, 0]) == 3 / 4
    assert tenant_isolation_rate([]) == 1.0
    assert tenant_isolation_rate([0, 0]) == 1.0
