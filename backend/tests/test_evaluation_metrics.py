
"""Unit tests for pure retrieval evaluation metrics."""

from uuid import UUID

import pytest

from app.evaluation.metrics import (
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
)

A = UUID(int=1)
B = UUID(int=2)
C = UUID(int=3)
D = UUID(int=4)
E = UUID(int=5)
F = UUID(int=6)


def test_precision_at_k():
    ranked = [A, D, B, E, F]
    relevant = {A, B, C}

    result = precision_at_k(ranked, relevant, k=5)

    assert result == pytest.approx(0.4)


def test_recall_at_k():
    ranked = [A, D, B, E, F]
    relevant = {A, B, C}

    result = recall_at_k(ranked, relevant, k=5)

    assert result == pytest.approx(2 / 3)


def test_reciprocal_rank_first_position():
    ranked = [A, D, B]
    relevant = {A, B}

    result = reciprocal_rank_at_k(ranked, relevant, k=3)

    assert result == 1.0


def test_reciprocal_rank_second_position():
    ranked = [D, A, B]
    relevant = {A, B}

    result = reciprocal_rank_at_k(ranked, relevant, k=3)

    assert result == 0.5


def test_no_relevant_results():
    ranked = [D, E, F]
    relevant = {A, B, C}

    assert precision_at_k(ranked, relevant, k=3) == 0.0
    assert recall_at_k(ranked, relevant, k=3) == 0.0
    assert reciprocal_rank_at_k(ranked, relevant, k=3) == 0.0


def test_fewer_results_than_k():
    ranked = [A]
    relevant = {A, B}

    assert precision_at_k(ranked, relevant, k=5) == pytest.approx(
        0.2
    )
    assert recall_at_k(ranked, relevant, k=5) == pytest.approx(
        0.5
    )
    assert reciprocal_rank_at_k(ranked, relevant, k=5) == 1.0


def test_empty_retrieval_results():
    ranked = []
    relevant = {A}

    assert precision_at_k(ranked, relevant, k=5) == 0.0
    assert recall_at_k(ranked, relevant, k=5) == 0.0
    assert reciprocal_rank_at_k(ranked, relevant, k=5) == 0.0


def test_relevant_result_outside_top_k():
    ranked = [D, E, A]
    relevant = {A}

    assert precision_at_k(ranked, relevant, k=2) == 0.0
    assert recall_at_k(ranked, relevant, k=2) == 0.0
    assert reciprocal_rank_at_k(ranked, relevant, k=2) == 0.0


@pytest.mark.parametrize(
    "metric",
    [
        precision_at_k,
        recall_at_k,
        reciprocal_rank_at_k,
    ],
)
def test_duplicate_ranked_ids_rejected(metric):
    with pytest.raises(
        ValueError,
        match="duplicates",
    ):
        metric([A, A], {A}, k=2)


@pytest.mark.parametrize(
    "invalid_k",
    [0, -1, True, 2.5],
)
def test_invalid_k_rejected(invalid_k):
    with pytest.raises(
        ValueError,
        match="positive integer",
    ):
        precision_at_k([A], {A}, k=invalid_k)


@pytest.mark.parametrize(
    "metric",
    [
        precision_at_k,
        recall_at_k,
        reciprocal_rank_at_k,
    ],
)
def test_empty_relevant_ids_rejected(metric):
    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        metric([A], set(), k=1)


def test_mean_reciprocal_rank():
    scores = [1.0, 0.5, 0.0]

    result = mean_reciprocal_rank(scores)

    assert result == pytest.approx(0.5)


def test_mean_reciprocal_rank_rejects_empty_input():
    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        mean_reciprocal_rank([])


@pytest.mark.parametrize(
    "invalid_score",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        -0.1,
        1.1,
    ],
)
def test_mean_reciprocal_rank_rejects_invalid_scores(
    invalid_score,
):
    with pytest.raises(
        ValueError,
        match="finite values between 0 and 1",
    ):
        mean_reciprocal_rank([invalid_score])
