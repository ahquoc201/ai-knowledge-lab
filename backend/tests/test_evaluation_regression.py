
"""Unit tests for retrieval quality regression detection."""

from copy import deepcopy
from math import nan

import pytest

from app.evaluation.regression import compare_retrieval_reports


def make_report() -> dict:
    """Create a valid baseline with two golden queries."""

    return {
        "schema_version": 1,
        "dataset_id": "ai-knowledge-lab-retrieval",
        "dataset_version": "1.0",
        "embedding_model": "intfloat/multilingual-e5-small",
        "retrieval_method": "semantic-search-pgvector",
        "evaluations": [
            {
                "k": 1,
                "mean_precision_at_k": 1.0,
                "mean_recall_at_k": 1.0,
                "mrr_at_k": 1.0,
                "cases": [
                    {
                        "case_id": "postgresql-001",
                        "precision_at_k": 1.0,
                        "recall_at_k": 1.0,
                        "reciprocal_rank_at_k": 1.0,
                    },
                    {
                        "case_id": "redis-001",
                        "precision_at_k": 1.0,
                        "recall_at_k": 1.0,
                        "reciprocal_rank_at_k": 1.0,
                    },
                ],
            }
        ],
    }


def test_identical_reports_have_no_regressions():
    baseline = make_report()
    candidate = deepcopy(baseline)

    findings = compare_retrieval_reports(
        baseline=baseline,
        candidate=candidate,
    )

    assert findings == ()


def test_improvements_are_not_regressions():
    baseline = make_report()
    candidate = deepcopy(baseline)

    baseline["evaluations"][0]["mrr_at_k"] = 0.5
    baseline["evaluations"][0]["cases"][0][
        "reciprocal_rank_at_k"
    ] = 0.5

    findings = compare_retrieval_reports(
        baseline=baseline,
        candidate=candidate,
    )

    assert findings == ()


def test_aggregate_metric_regression_detected():
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["evaluations"][0]["mean_recall_at_k"] = 0.75

    findings = compare_retrieval_reports(
        baseline=baseline,
        candidate=candidate,
    )

    assert len(findings) == 1

    finding = findings[0]

    assert finding.k == 1
    assert finding.case_id is None
    assert finding.metric == "mean_recall_at_k"
    assert finding.baseline == 1.0
    assert finding.candidate == 0.75
    assert finding.drop == 0.25


def test_query_regression_detected_even_when_average_is_unchanged():
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["evaluations"][0]["cases"][1][
        "reciprocal_rank_at_k"
    ] = 0.5

    findings = compare_retrieval_reports(
        baseline=baseline,
        candidate=candidate,
    )

    assert len(findings) == 1
    assert findings[0].case_id == "redis-001"
    assert findings[0].metric == "reciprocal_rank_at_k"
    assert findings[0].drop == 0.5


def test_multiple_regressions_detected():
    baseline = make_report()
    candidate = deepcopy(baseline)

    current = candidate["evaluations"][0]

    current["mean_precision_at_k"] = 0.5
    current["mrr_at_k"] = 0.75
    current["cases"][0]["precision_at_k"] = 0.0

    findings = compare_retrieval_reports(
        baseline=baseline,
        candidate=candidate,
    )

    assert len(findings) == 3

    assert {finding.metric for finding in findings} == {
        "mean_precision_at_k",
        "mrr_at_k",
        "precision_at_k",
    }


def test_allowed_drop_respected():
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["evaluations"][0]["mrr_at_k"] = 0.75

    tolerated = compare_retrieval_reports(
        baseline=baseline,
        candidate=candidate,
        allowed_drop=0.25,
    )

    strict = compare_retrieval_reports(
        baseline=baseline,
        candidate=candidate,
        allowed_drop=0.0,
    )

    assert tolerated == ()
    assert len(strict) == 1


def test_embedding_model_change_is_allowed():
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["embedding_model"] = "another-embedding-model"
    candidate["retrieval_method"] = "hybrid-search"

    assert compare_retrieval_reports(
        baseline=baseline,
        candidate=candidate,
    ) == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dataset_id", "different-dataset"),
        ("dataset_version", "2.0"),
    ],
)
def test_different_datasets_rejected(field, value):
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate[field] = value

    with pytest.raises(ValueError, match="Report mismatch"):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


def test_different_k_values_rejected():
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["evaluations"][0]["k"] = 3

    with pytest.raises(
        ValueError,
        match="different K values",
    ):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


def test_different_case_ids_rejected():
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["evaluations"][0]["cases"][1][
        "case_id"
    ] = "unknown-query"

    with pytest.raises(
        ValueError,
        match="different case IDs",
    ):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


def test_duplicate_k_rejected():
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["evaluations"].append(
        deepcopy(candidate["evaluations"][0])
    )

    with pytest.raises(ValueError, match="Duplicate k"):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


def test_duplicate_case_id_rejected():
    baseline = make_report()
    candidate = deepcopy(baseline)

    cases = candidate["evaluations"][0]["cases"]
    cases.append(deepcopy(cases[0]))

    with pytest.raises(ValueError, match="Duplicate case_id"):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


def test_unsupported_schema_version_rejected():
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["schema_version"] = 2

    with pytest.raises(
        ValueError,
        match="Unsupported report schema",
    ):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


@pytest.mark.parametrize(
    "invalid_score",
    [
        -0.1,
        1.1,
        nan,
        True,
        "0.5",
    ],
)
def test_invalid_scores_rejected(invalid_score):
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["evaluations"][0]["mrr_at_k"] = invalid_score

    with pytest.raises(ValueError, match="Invalid score"):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


@pytest.mark.parametrize(
    "invalid_tolerance",
    [
        -0.1,
        1.1,
        nan,
        True,
    ],
)
def test_invalid_tolerance_rejected(invalid_tolerance):
    with pytest.raises(
        ValueError,
        match="allowed_drop",
    ):
        compare_retrieval_reports(
            baseline=make_report(),
            candidate=make_report(),
            allowed_drop=invalid_tolerance,
        )


def test_empty_evaluations_rejected():
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["evaluations"] = []

    with pytest.raises(ValueError, match="non-empty list"):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


def test_missing_metric_rejected():
    baseline = make_report()
    candidate = deepcopy(baseline)

    del candidate["evaluations"][0]["mrr_at_k"]

    with pytest.raises(ValueError, match="Invalid score"):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


@pytest.mark.parametrize(
    "field",
    ["dataset_id", "dataset_version"],
)
def test_missing_metadata_in_both_reports_rejected(field):
    """Two reports missing the same field must not pass."""

    baseline = make_report()
    candidate = deepcopy(baseline)

    del baseline[field]
    del candidate[field]

    with pytest.raises(
        ValueError,
        match="Missing or invalid report metadata",
    ):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


@pytest.mark.parametrize(
    "invalid_value",
    ["", "   ", None, 123],
)
def test_invalid_dataset_metadata_rejected(invalid_value):
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["dataset_id"] = invalid_value

    with pytest.raises(
        ValueError,
        match="Missing or invalid report metadata",
    ):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


@pytest.mark.parametrize(
    "invalid_version",
    [True, 1.0, "1", None],
)
def test_invalid_schema_version_rejected(invalid_version):
    baseline = make_report()
    candidate = deepcopy(baseline)

    candidate["schema_version"] = invalid_version

    with pytest.raises(
        ValueError,
        match="Unsupported report schema version",
    ):
        compare_retrieval_reports(
            baseline=baseline,
            candidate=candidate,
        )


def test_non_object_report_rejected():
    with pytest.raises(
        TypeError,
        match="Reports must be JSON objects",
    ):
        compare_retrieval_reports(
            baseline=[],
            candidate=make_report(),
        )
