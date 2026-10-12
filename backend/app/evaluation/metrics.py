
"""Pure retrieval evaluation metrics."""

from collections.abc import Collection, Sequence
from math import isfinite
from uuid import UUID


def _validate_retrieval_inputs(
    ranked_chunk_ids: Sequence[UUID],
    relevant_chunk_ids: Collection[UUID],
    k: int,
) -> None:
    """Validate inputs shared by retrieval metrics."""

    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")

    if not relevant_chunk_ids:
        raise ValueError("relevant_chunk_ids must not be empty")

    if len(set(ranked_chunk_ids)) != len(ranked_chunk_ids):
        raise ValueError("ranked_chunk_ids contains duplicates")


def precision_at_k(
    ranked_chunk_ids: Sequence[UUID],
    relevant_chunk_ids: Collection[UUID],
    k: int,
) -> float:
    """Return the fraction of relevant results in the top k."""

    _validate_retrieval_inputs(
        ranked_chunk_ids,
        relevant_chunk_ids,
        k,
    )

    relevant = set(relevant_chunk_ids)
    top_k = ranked_chunk_ids[:k]

    hits = sum(
        chunk_id in relevant
        for chunk_id in top_k
    )

    return hits / k


def recall_at_k(
    ranked_chunk_ids: Sequence[UUID],
    relevant_chunk_ids: Collection[UUID],
    k: int,
) -> float:
    """Return the fraction of all relevant chunks found in top k."""

    _validate_retrieval_inputs(
        ranked_chunk_ids,
        relevant_chunk_ids,
        k,
    )

    relevant = set(relevant_chunk_ids)
    top_k = ranked_chunk_ids[:k]

    hits = sum(
        chunk_id in relevant
        for chunk_id in top_k
    )

    return hits / len(relevant)


def reciprocal_rank_at_k(
    ranked_chunk_ids: Sequence[UUID],
    relevant_chunk_ids: Collection[UUID],
    k: int,
) -> float:
    """Return reciprocal rank of the first relevant result."""

    _validate_retrieval_inputs(
        ranked_chunk_ids,
        relevant_chunk_ids,
        k,
    )

    relevant = set(relevant_chunk_ids)

    for rank, chunk_id in enumerate(
        ranked_chunk_ids[:k],
        start=1,
    ):
        if chunk_id in relevant:
            return 1.0 / rank

    return 0.0


def mean_reciprocal_rank(
    reciprocal_ranks: Sequence[float],
) -> float:
    """Average reciprocal ranks across evaluation queries."""

    if not reciprocal_ranks:
        raise ValueError("reciprocal_ranks must not be empty")

    if any(
        not isfinite(score) or not 0.0 <= score <= 1.0
        for score in reciprocal_ranks
    ):
        raise ValueError(
            "reciprocal ranks must be finite values between 0 and 1"
        )

    return sum(reciprocal_ranks) / len(reciprocal_ranks)
