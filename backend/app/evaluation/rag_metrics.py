"""Pure retrieval evaluation metrics for RAG quality benchmarks (T260030).

Implements deterministic metrics for:
- Recall@K
- Precision@K
- Reciprocal Rank@K / MRR@K
- Retrieval Coverage
- Empty Retrieval Rate
- Tenant Isolation Rate
"""

from collections.abc import Collection, Sequence
from math import isfinite


def _validate_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")


def hit_rate_at_k(
    retrieved_keys: Sequence[str],
    expected_keys: Collection[str],
    k: int,
) -> float:
    """Calculate Hit Rate@K: binary indicator (1.0 or 0.0) if at least one expected item is in top-k.

    Formula: 1.0 if |Retrieved[:k] ∩ Expected| > 0 else 0.0
    Raises ValueError if expected_keys is empty.
    """
    _validate_k(k)
    if not expected_keys:
        raise ValueError("expected_keys must not be empty for hit rate calculation")

    top_k = retrieved_keys[:k]
    expected_set = set(expected_keys)
    return 1.0 if any(item in expected_set for item in top_k) else 0.0


def precision_at_k(
    retrieved_keys: Sequence[str],
    expected_keys: Collection[str],
    k: int,
) -> float:
    """Calculate Precision@K: fraction of top-k retrieved items that are relevant.

    Formula: |Retrieved[:k] ∩ Expected| / k
    If expected_keys is empty, returns 0.0 (no relevant items exist).
    """
    _validate_k(k)
    if not expected_keys:
        return 0.0

    top_k = retrieved_keys[:k]
    expected_set = set(expected_keys)
    hits = sum(1 for item in top_k if item in expected_set)
    return hits / k


def recall_at_k(
    retrieved_keys: Sequence[str],
    expected_keys: Collection[str],
    k: int,
) -> float:
    """Calculate Recall@K: fraction of expected relevant items found in top-k.

    Formula: |Retrieved[:k] ∩ Expected| / |Expected|
    Raises ValueError if expected_keys is empty because denominator is undefined.
    """
    _validate_k(k)
    if not expected_keys:
        raise ValueError("expected_keys must not be empty for recall calculation")

    top_k = retrieved_keys[:k]
    expected_set = set(expected_keys)
    hits = sum(1 for item in top_k if item in expected_set)
    return hits / len(expected_set)


def reciprocal_rank_at_k(
    retrieved_keys: Sequence[str],
    expected_keys: Collection[str],
    k: int,
) -> float:
    """Calculate Reciprocal Rank@K of the first relevant retrieved item.

    Formula: 1 / rank if rank <= k else 0.0
    If expected_keys is empty, returns 0.0.
    """
    _validate_k(k)
    if not expected_keys:
        return 0.0

    expected_set = set(expected_keys)
    for rank, key in enumerate(retrieved_keys[:k], start=1):
        if key in expected_set:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(reciprocal_ranks: Sequence[float]) -> float:
    """Calculate Mean Reciprocal Rank (MRR) across queries."""
    if not reciprocal_ranks:
        return 0.0

    for score in reciprocal_ranks:
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not isfinite(score)
            or not 0 <= score <= 1
        ):
            raise ValueError(f"Invalid reciprocal rank score: {score!r}")

    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def retrieval_coverage(
    case_hits_list: Sequence[int],
) -> float:
    """Calculate Retrieval Coverage: fraction of answerable queries where at least one relevant item was retrieved.

    Formula: Count(hits > 0) / Total Answerable Queries
    """
    if not case_hits_list:
        return 0.0

    successful_retrievals = sum(1 for hits in case_hits_list if hits > 0)
    return successful_retrievals / len(case_hits_list)


def empty_retrieval_rate(
    retrieved_counts: Sequence[int],
) -> float:
    """Calculate Empty Retrieval Rate: fraction of queries returning 0 chunks.

    Formula: Count(retrieved == 0) / Total Queries
    """
    if not retrieved_counts:
        return 0.0

    empty_count = sum(1 for count in retrieved_counts if count == 0)
    return empty_count / len(retrieved_counts)


def empty_candidate_rate(
    candidate_counts: Sequence[int],
) -> float:
    """Calculate Empty Candidate Rate: fraction of queries returning 0 candidates from vector search.

    Formula: Count(candidates == 0) / Total Queries
    """
    if not candidate_counts:
        return 0.0

    empty_count = sum(1 for count in candidate_counts if count == 0)
    return empty_count / len(candidate_counts)


def empty_accepted_evidence_rate(
    accepted_counts: Sequence[int],
) -> float:
    """Calculate Empty Accepted Evidence Rate: fraction of queries where 0 evidence chunks fit into context.

    Formula: Count(accepted == 0) / Total Queries
    """
    if not accepted_counts:
        return 0.0

    empty_count = sum(1 for count in accepted_counts if count == 0)
    return empty_count / len(accepted_counts)


def tenant_isolation_rate(
    cross_tenant_violation_counts: Sequence[int],
) -> float:
    """Calculate Tenant Isolation Rate: fraction of queries with 0 cross-tenant chunks.

    Formula: Count(cross_tenant_violations == 0) / Total Queries
    """
    if not cross_tenant_violation_counts:
        return 1.0

    clean_queries = sum(1 for count in cross_tenant_violation_counts if count == 0)
    return clean_queries / len(cross_tenant_violation_counts)
