
"""Tests for retrieval regression comparison CLI."""

import json
from copy import deepcopy

import pytest

from app.evaluation.compare_cli import main


def make_report() -> dict:
    return {
        "schema_version": 1,
        "dataset_id": "retrieval-test",
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
                        "case_id": "query-001",
                        "precision_at_k": 1.0,
                        "recall_at_k": 1.0,
                        "reciprocal_rank_at_k": 1.0,
                    }
                ],
            }
        ],
    }


@pytest.fixture
def report_paths(tmp_path):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"

    report = make_report()
    baseline.write_text(
        json.dumps(report),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps(report),
        encoding="utf-8",
    )

    return baseline, candidate


def run_cli(baseline, candidate, *extra_args):
    return main(
        [
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            *extra_args,
        ]
    )


def write_candidate(path, report):
    path.write_text(
        json.dumps(report),
        encoding="utf-8",
    )


def test_identical_reports_pass(report_paths, capsys):
    baseline, candidate = report_paths

    exit_code = run_cli(baseline, candidate)

    output = capsys.readouterr()

    assert exit_code == 0
    assert "PASS: No retrieval regressions detected" in output.out
    assert output.err == ""


def test_aggregate_regression_returns_exit_code_1(
    report_paths,
    capsys,
):
    baseline, candidate = report_paths

    report = make_report()
    report["evaluations"][0]["mrr_at_k"] = 0.5
    write_candidate(candidate, report)

    exit_code = run_cli(baseline, candidate)

    output = capsys.readouterr()

    assert exit_code == 1
    assert "FAIL: Detected 1" in output.out
    assert "metric=mrr_at_k" in output.out
    assert "case=aggregate" in output.out


def test_query_regression_detected_even_if_average_unchanged(
    report_paths,
    capsys,
):
    baseline, candidate = report_paths

    report = make_report()
    report["evaluations"][0]["cases"][0][
        "reciprocal_rank_at_k"
    ] = 0.5
    write_candidate(candidate, report)

    exit_code = run_cli(baseline, candidate)

    output = capsys.readouterr()

    assert exit_code == 1
    assert "case=query-001" in output.out
    assert "metric=reciprocal_rank_at_k" in output.out


def test_allowed_drop_passes_within_tolerance(
    report_paths,
    capsys,
):
    baseline, candidate = report_paths

    report = make_report()
    report["evaluations"][0]["mrr_at_k"] = 0.75
    write_candidate(candidate, report)

    exit_code = run_cli(
        baseline,
        candidate,
        "--allowed-drop",
        "0.25",
    )

    assert exit_code == 0
    assert "PASS" in capsys.readouterr().out


def test_drop_exceeding_tolerance_fails(report_paths):
    baseline, candidate = report_paths

    report = make_report()
    report["evaluations"][0]["mrr_at_k"] = 0.5
    write_candidate(candidate, report)

    assert run_cli(
        baseline,
        candidate,
        "--allowed-drop",
        "0.25",
    ) == 1


def test_dataset_version_mismatch_rejected(
    report_paths,
    capsys,
):
    baseline, candidate = report_paths

    report = make_report()
    report["dataset_version"] = "2.0"
    write_candidate(candidate, report)

    assert run_cli(baseline, candidate) == 1
    assert "Report mismatch" in capsys.readouterr().err


def test_different_k_values_rejected(report_paths, capsys):
    baseline, candidate = report_paths

    report = make_report()
    report["evaluations"][0]["k"] = 3
    write_candidate(candidate, report)

    assert run_cli(baseline, candidate) == 1
    assert "different K values" in capsys.readouterr().err


def test_invalid_json_rejected(report_paths, capsys):
    baseline, candidate = report_paths

    candidate.write_text(
        "{invalid json",
        encoding="utf-8",
    )

    assert run_cli(baseline, candidate) == 1
    assert "INVALID REPORT" in capsys.readouterr().err


def test_json_array_rejected(report_paths, capsys):
    baseline, candidate = report_paths

    candidate.write_text(
        "[]",
        encoding="utf-8",
    )

    assert run_cli(baseline, candidate) == 1
    assert "Report must be a JSON object" in (
        capsys.readouterr().err
    )


def test_missing_candidate_file_rejected(
    report_paths,
    capsys,
):
    baseline, candidate = report_paths
    candidate.unlink()

    assert run_cli(baseline, candidate) == 1
    assert "INVALID REPORT" in capsys.readouterr().err


def test_unsupported_schema_rejected(report_paths, capsys):
    baseline, candidate = report_paths

    report = make_report()
    report["schema_version"] = 2
    write_candidate(candidate, report)

    assert run_cli(baseline, candidate) == 1
    assert "Unsupported report schema" in (
        capsys.readouterr().err
    )


def test_invalid_tolerance_rejected(report_paths, capsys):
    baseline, candidate = report_paths

    assert run_cli(
        baseline,
        candidate,
        "--allowed-drop",
        "-0.1",
    ) == 1

    assert "allowed_drop" in capsys.readouterr().err


def test_missing_metric_rejected(report_paths, capsys):
    baseline, candidate = report_paths

    report = deepcopy(make_report())
    del report["evaluations"][0]["mrr_at_k"]
    write_candidate(candidate, report)

    assert run_cli(baseline, candidate) == 1
    assert "Invalid score" in capsys.readouterr().err
