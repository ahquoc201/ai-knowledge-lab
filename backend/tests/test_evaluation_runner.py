
"""Unit tests for the retrieval evaluation runner."""

from uuid import UUID

import pytest

from app.evaluation.models import (
    GoldenDataset,
    GoldenQuery,
)
from app.evaluation.runner import run_retrieval_evaluation

A = UUID(int=1)
B = UUID(int=2)
C = UUID(int=3)
D = UUID(int=4)
E = UUID(int=5)
F = UUID(int=6)


class FakeRetriever:
    """Deterministic retriever for evaluation tests."""

    def __init__(
        self,
        responses: dict[str, list[UUID]],
    ) -> None:
        self.responses = responses
        self.calls: list[tuple[str, int]] = []

    async def __call__(
        self,
        query: str,
        limit: int,
    ) -> list[UUID]:
        self.calls.append((query, limit))
        return self.responses.get(query, [])


def make_dataset() -> GoldenDataset:
    return GoldenDataset(
        dataset_id="retrieval-baseline",
        version="1.0",
        cases=(
            GoldenQuery(
                case_id="q1",
                query="What is PostgreSQL?",
                relevant_chunk_ids=frozenset({A, B}),
            ),
            GoldenQuery(
                case_id="q2",
                query="What is FastAPI?",
                relevant_chunk_ids=frozenset({D, E}),
            ),
            GoldenQuery(
                case_id="q3",
                query="What is Redis?",
                relevant_chunk_ids=frozenset({E}),
            ),
        ),
    )


@pytest.mark.anyio
async def test_runner_evaluates_multiple_queries():
    dataset = make_dataset()

    retriever = FakeRetriever(
        {
            "What is PostgreSQL?": [A, C, B],
            "What is FastAPI?": [C, D, F],
            "What is Redis?": [C, F, A],
        }
    )

    report = await run_retrieval_evaluation(
        dataset=dataset,
        retriever=retriever,
        k=3,
    )

    assert report.dataset_id == "retrieval-baseline"
    assert report.dataset_version == "1.0"
    assert report.k == 3
    assert len(report.results) == 3

    first, second, third = report.results

    # Query 1: two relevant chunks; first at rank 1.
    assert first.case_id == "q1"
    assert first.precision_at_k == pytest.approx(2 / 3)
    assert first.recall_at_k == 1.0
    assert first.reciprocal_rank_at_k == 1.0

    # Query 2: one relevant chunk; first at rank 2.
    assert second.case_id == "q2"
    assert second.precision_at_k == pytest.approx(1 / 3)
    assert second.recall_at_k == 0.5
    assert second.reciprocal_rank_at_k == 0.5

    # Query 3: no relevant chunks retrieved.
    assert third.case_id == "q3"
    assert third.precision_at_k == 0.0
    assert third.recall_at_k == 0.0
    assert third.reciprocal_rank_at_k == 0.0

    # Macro-average: each question contributes equally.
    assert report.mean_precision_at_k == pytest.approx(1 / 3)
    assert report.mean_recall_at_k == pytest.approx(0.5)
    assert report.mrr_at_k == pytest.approx(0.5)


@pytest.mark.anyio
async def test_runner_preserves_case_and_ranking_order():
    dataset = make_dataset()

    retriever = FakeRetriever(
        {
            "What is PostgreSQL?": [C, A, B],
            "What is FastAPI?": [D, C],
            "What is Redis?": [E],
        }
    )

    report = await run_retrieval_evaluation(
        dataset=dataset,
        retriever=retriever,
        k=3,
    )

    assert [result.case_id for result in report.results] == [
        "q1",
        "q2",
        "q3",
    ]

    assert report.results[0].ranked_chunk_ids == (C, A, B)
    assert report.results[1].ranked_chunk_ids == (D, C)
    assert report.results[2].ranked_chunk_ids == (E,)

    assert retriever.calls == [
        ("What is PostgreSQL?", 3),
        ("What is FastAPI?", 3),
        ("What is Redis?", 3),
    ]


@pytest.mark.anyio
async def test_runner_ignores_results_outside_top_k():
    dataset = GoldenDataset(
        dataset_id="top-k-test",
        version="1.0",
        cases=(
            GoldenQuery(
                case_id="q1",
                query="Test question",
                relevant_chunk_ids=frozenset({A}),
            ),
        ),
    )

    retriever = FakeRetriever(
        {
            "Test question": [C, D, A],
        }
    )

    report = await run_retrieval_evaluation(
        dataset=dataset,
        retriever=retriever,
        k=2,
    )

    result = report.results[0]

    assert result.ranked_chunk_ids == (C, D)
    assert result.precision_at_k == 0.0
    assert result.recall_at_k == 0.0
    assert result.reciprocal_rank_at_k == 0.0


@pytest.mark.anyio
async def test_runner_handles_empty_retrieval():
    dataset = make_dataset()
    retriever = FakeRetriever({})

    report = await run_retrieval_evaluation(
        dataset=dataset,
        retriever=retriever,
        k=5,
    )

    assert all(
        result.ranked_chunk_ids == ()
        for result in report.results
    )

    assert report.mean_precision_at_k == 0.0
    assert report.mean_recall_at_k == 0.0
    assert report.mrr_at_k == 0.0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_k",
    [0, -1, True, 2.5],
)
async def test_runner_rejects_invalid_k(invalid_k):
    dataset = make_dataset()
    retriever = FakeRetriever({})

    with pytest.raises(
        ValueError,
        match="k must be a positive integer",
    ):
        await run_retrieval_evaluation(
            dataset=dataset,
            retriever=retriever,
            k=invalid_k,
        )

    # Validation must happen before retrieval.
    assert retriever.calls == []


@pytest.mark.anyio
async def test_runner_rejects_duplicate_ranked_chunks():
    dataset = GoldenDataset(
        dataset_id="duplicate-test",
        version="1.0",
        cases=(
            GoldenQuery(
                case_id="q1",
                query="Test question",
                relevant_chunk_ids=frozenset({A}),
            ),
        ),
    )

    retriever = FakeRetriever(
        {
            "Test question": [A, A],
        }
    )

    with pytest.raises(
        ValueError,
        match="duplicates",
    ):
        await run_retrieval_evaluation(
            dataset=dataset,
            retriever=retriever,
            k=2,
        )


@pytest.mark.anyio
async def test_runner_propagates_retriever_error():
    dataset = make_dataset()

    class FailingRetriever:
        async def __call__(
            self,
            query: str,
            limit: int,
        ) -> list[UUID]:
            raise RuntimeError("Vector database unavailable")

    with pytest.raises(
        RuntimeError,
        match="Vector database unavailable",
    ):
        await run_retrieval_evaluation(
            dataset=dataset,
            retriever=FailingRetriever(),
            k=5,
        )
