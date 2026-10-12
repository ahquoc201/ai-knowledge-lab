
"""Serialize portable retrieval evaluation reports."""

from collections.abc import Sequence

from app.evaluation.models import EvaluationReport


def build_baseline_report(
    *,
    reports: Sequence[EvaluationReport],
    embedding_model: str,
    retrieval_method: str,
) -> dict:
    """Build a stable report without temporary database UUIDs."""

    if not reports:
        raise ValueError("At least one evaluation report is required")

    if not embedding_model.strip():
        raise ValueError("embedding_model must not be empty")

    if not retrieval_method.strip():
        raise ValueError("retrieval_method must not be empty")

    first = reports[0]
    seen_k: set[int] = set()
    expected_case_ids = {
        result.case_id for result in first.results
    }

    for report in reports:
        if (
            report.dataset_id != first.dataset_id
            or report.dataset_version != first.dataset_version
        ):
            raise ValueError("Evaluation reports use different datasets")

        if report.k in seen_k:
            raise ValueError(f"Duplicate evaluation k: {report.k}")

        seen_k.add(report.k)

        case_ids = {
            result.case_id for result in report.results
        }

        if case_ids != expected_case_ids:
            raise ValueError(
                "Evaluation reports contain different case IDs"
            )

    evaluations = []

    for report in sorted(reports, key=lambda item: item.k):
        evaluations.append(
            {
                "k": report.k,
                "mean_precision_at_k": report.mean_precision_at_k,
                "mean_recall_at_k": report.mean_recall_at_k,
                "mrr_at_k": report.mrr_at_k,
                "cases": [
                    {
                        "case_id": result.case_id,
                        "precision_at_k": result.precision_at_k,
                        "recall_at_k": result.recall_at_k,
                        "reciprocal_rank_at_k": (
                            result.reciprocal_rank_at_k
                        ),
                        "relevant_chunk_count": len(
                            result.relevant_chunk_ids
                        ),
                        "retrieved_chunk_count": len(
                            result.ranked_chunk_ids
                        ),
                    }
                    for result in report.results
                ],
            }
        )

    return {
        "schema_version": 1,
        "dataset_id": first.dataset_id,
        "dataset_version": first.dataset_version,
        "embedding_model": embedding_model,
        "retrieval_method": retrieval_method,
        "evaluations": evaluations,
    }
