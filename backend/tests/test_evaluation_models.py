
"""Unit tests for retrieval evaluation data models."""

from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from app.evaluation.models import (
    EvaluationReport,
    GoldenDataset,
    GoldenQuery,
    QueryEvaluationResult,
)

A = UUID(int=1)
B = UUID(int=2)
C = UUID(int=3)


def make_case(
    case_id: str = "case-001",
) -> GoldenQuery:
    return GoldenQuery(
        case_id=case_id,
        query="What is PostgreSQL?",
        relevant_chunk_ids=frozenset({A, B}),
    )


def test_golden_query_creation():
    case = make_case()

    assert case.case_id == "case-001"
    assert case.query == "What is PostgreSQL?"
    assert case.relevant_chunk_ids == frozenset({A, B})


def test_golden_query_normalizes_relevant_ids():
    case = GoldenQuery(
        case_id="case-001",
        query="What is PostgreSQL?",
        relevant_chunk_ids=[A, A, B],
    )

    assert case.relevant_chunk_ids == frozenset({A, B})
    assert isinstance(case.relevant_chunk_ids, frozenset)


@pytest.mark.parametrize(
    ("case_id", "query", "relevant_ids", "message"),
    [
        ("", "Question", {A}, "case_id must not be empty"),
        ("   ", "Question", {A}, "case_id must not be empty"),
        ("case-1", "", {A}, "query must not be empty"),
        ("case-1", "   ", {A}, "query must not be empty"),
        (
            "case-1",
            "Question",
            set(),
            "relevant_chunk_ids must not be empty",
        ),
    ],
)
def test_golden_query_rejects_invalid_input(
    case_id,
    query,
    relevant_ids,
    message,
):
    with pytest.raises(ValueError, match=message):
        GoldenQuery(
            case_id=case_id,
            query=query,
            relevant_chunk_ids=relevant_ids,
        )


def test_golden_query_is_immutable():
    case = make_case()

    with pytest.raises(FrozenInstanceError):
        case.query = "Changed question"

    assert not hasattr(case, "__dict__")


def test_golden_dataset_creation():
    first = make_case("case-001")
    second = make_case("case-002")

    dataset = GoldenDataset(
        dataset_id="retrieval-baseline",
        version="1.0",
        cases=(first, second),
    )

    assert dataset.dataset_id == "retrieval-baseline"
    assert dataset.version == "1.0"
    assert len(dataset.cases) == 2
    assert dataset.cases[0] is first
    assert dataset.cases[1] is second


def test_golden_dataset_normalizes_cases():
    case = make_case()

    dataset = GoldenDataset(
        dataset_id="baseline",
        version="1.0",
        cases=[case],
    )

    assert isinstance(dataset.cases, tuple)
    assert dataset.cases == (case,)


def test_golden_dataset_rejects_duplicate_case_ids():
    first = make_case("duplicate")
    second = make_case("duplicate")

    with pytest.raises(
        ValueError,
        match="Duplicate evaluation case IDs",
    ):
        GoldenDataset(
            dataset_id="baseline",
            version="1.0",
            cases=(first, second),
        )


@pytest.mark.parametrize(
    ("dataset_id", "version", "cases", "message"),
    [
        (
            "",
            "1.0",
            (make_case(),),
            "dataset_id must not be empty",
        ),
        (
            "baseline",
            "   ",
            (make_case(),),
            "version must not be empty",
        ),
        (
            "baseline",
            "1.0",
            (),
            "cases must not be empty",
        ),
    ],
)
def test_golden_dataset_rejects_invalid_input(
    dataset_id,
    version,
    cases,
    message,
):
    with pytest.raises(ValueError, match=message):
        GoldenDataset(
            dataset_id=dataset_id,
            version=version,
            cases=cases,
        )


def test_golden_dataset_is_immutable():
    dataset = GoldenDataset(
        dataset_id="baseline",
        version="1.0",
        cases=(make_case(),),
    )

    with pytest.raises(FrozenInstanceError):
        dataset.version = "2.0"

    assert not hasattr(dataset, "__dict__")


def test_query_evaluation_result():
    result = QueryEvaluationResult(
        case_id="case-001",
        query="What is PostgreSQL?",
        ranked_chunk_ids=(A, C, B),
        relevant_chunk_ids=frozenset({A, B}),
        precision_at_k=2 / 3,
        recall_at_k=1.0,
        reciprocal_rank_at_k=1.0,
    )

    assert result.case_id == "case-001"
    assert result.ranked_chunk_ids == (A, C, B)
    assert result.precision_at_k == pytest.approx(2 / 3)
    assert result.recall_at_k == 1.0

    with pytest.raises(FrozenInstanceError):
        result.precision_at_k = 0.0


def test_evaluation_report():
    query_result = QueryEvaluationResult(
        case_id="case-001",
        query="What is PostgreSQL?",
        ranked_chunk_ids=(A, C, B),
        relevant_chunk_ids=frozenset({A, B}),
        precision_at_k=2 / 3,
        recall_at_k=1.0,
        reciprocal_rank_at_k=1.0,
    )

    report = EvaluationReport(
        dataset_id="baseline",
        dataset_version="1.0",
        k=3,
        results=(query_result,),
        mean_precision_at_k=2 / 3,
        mean_recall_at_k=1.0,
        mrr_at_k=1.0,
    )

    assert report.dataset_id == "baseline"
    assert report.dataset_version == "1.0"
    assert report.k == 3
    assert len(report.results) == 1
    assert report.results[0] is query_result

    with pytest.raises(FrozenInstanceError):
        report.k = 5
