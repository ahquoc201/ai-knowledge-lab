
"""Tests for portable retrieval evaluation reporting."""

import json
from uuid import UUID

import pytest

from app.evaluation.models import (
    EvaluationReport,
    QueryEvaluationResult,
)
from app.evaluation.reporting import build_baseline_report


def make_report(
    *,
    k: int = 1,
    dataset_id: str = "retrieval-test",
    dataset_version: str = "1.0",
    case_id: str = "query-001",
) -> EvaluationReport:
    relevant_id = UUID(int=1)
    irrelevant_id = UUID(int=2)

    ranked_ids = (
        (relevant_id,)
        if k == 1
        else (relevant_id, irrelevant_id)
    )

    result = QueryEvaluationResult(
        case_id=case_id,
        query="How does PostgreSQL handle transactions?",
        ranked_chunk_ids=ranked_ids,
        relevant_chunk_ids=frozenset({relevant_id}),
        precision_at_k=1.0 / k,
        recall_at_k=1.0,
        reciprocal_rank_at_k=1.0,
    )

    return EvaluationReport(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        k=k,
        results=(result,),
        mean_precision_at_k=1.0 / k,
        mean_recall_at_k=1.0,
        mrr_at_k=1.0,
    )


def build_report(*reports: EvaluationReport) -> dict:
    return build_baseline_report(
        reports=reports,
        embedding_model="multilingual-e5-small",
        retrieval_method="pgvector-cosine",
    )


def test_report_contains_metadata():
    report = build_report(make_report())

    assert report["schema_version"] == 1
    assert report["dataset_id"] == "retrieval-test"
    assert report["dataset_version"] == "1.0"
    assert report["embedding_model"] == "multilingual-e5-small"
    assert report["retrieval_method"] == "pgvector-cosine"


def test_evaluations_sorted_by_k():
    report = build_report(
        make_report(k=3),
        make_report(k=1),
    )

    assert [
        evaluation["k"]
        for evaluation in report["evaluations"]
    ] == [1, 3]


def test_report_contains_correct_metrics():
    report = build_report(make_report(k=3))

    evaluation = report["evaluations"][0]

    assert evaluation["mean_precision_at_k"] == pytest.approx(
        1.0 / 3
    )
    assert evaluation["mean_recall_at_k"] == 1.0
    assert evaluation["mrr_at_k"] == 1.0

    case = evaluation["cases"][0]

    assert case["case_id"] == "query-001"
    assert case["precision_at_k"] == pytest.approx(1.0 / 3)
    assert case["recall_at_k"] == 1.0
    assert case["reciprocal_rank_at_k"] == 1.0
    assert case["relevant_chunk_count"] == 1
    assert case["retrieved_chunk_count"] == 2


def test_report_does_not_expose_temporary_chunk_ids():
    report = build_report(make_report())

    serialized = json.dumps(report)

    assert str(UUID(int=1)) not in serialized
    assert str(UUID(int=2)) not in serialized
    assert "ranked_chunk_ids" not in serialized
    assert "relevant_chunk_ids" not in serialized


def test_report_is_json_serializable():
    report = build_report(
        make_report(k=1),
        make_report(k=3),
    )

    restored = json.loads(json.dumps(report))

    assert restored == report


def test_empty_reports_rejected():
    with pytest.raises(
        ValueError,
        match="At least one evaluation report",
    ):
        build_report()


@pytest.mark.parametrize(
    ("embedding_model", "retrieval_method"),
    [
        ("", "pgvector-cosine"),
        ("   ", "pgvector-cosine"),
        ("multilingual-e5-small", ""),
        ("multilingual-e5-small", "   "),
    ],
)
def test_empty_model_or_method_rejected(
    embedding_model,
    retrieval_method,
):
    with pytest.raises(ValueError):
        build_baseline_report(
            reports=[make_report()],
            embedding_model=embedding_model,
            retrieval_method=retrieval_method,
        )


@pytest.mark.parametrize(
    ("dataset_id", "dataset_version"),
    [
        ("another-dataset", "1.0"),
        ("retrieval-test", "2.0"),
    ],
)
def test_mixed_dataset_metadata_rejected(
    dataset_id,
    dataset_version,
):
    with pytest.raises(
        ValueError,
        match="different datasets",
    ):
        build_report(
            make_report(k=1),
            make_report(
                k=3,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
            ),
        )


def test_duplicate_k_rejected():
    with pytest.raises(
        ValueError,
        match="Duplicate evaluation k",
    ):
        build_report(
            make_report(k=1),
            make_report(k=1),
        )


def test_different_case_ids_rejected():
    with pytest.raises(
        ValueError,
        match="different case IDs",
    ):
        build_report(
            make_report(k=1, case_id="query-001"),
            make_report(k=3, case_id="query-002"),
        )
