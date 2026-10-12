
"""Detect retrieval quality regressions against a saved baseline."""

from dataclasses import dataclass
from math import isfinite

AGGREGATE_METRICS = (
    "mean_precision_at_k",
    "mean_recall_at_k",
    "mrr_at_k",
)

QUERY_METRICS = (
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank_at_k",
)


@dataclass(frozen=True, slots=True)
class RegressionFinding:
    """A metric that decreased beyond the allowed tolerance."""

    k: int
    case_id: str | None
    metric: str
    baseline: float
    candidate: float

    @property
    def drop(self) -> float:
        return self.baseline - self.candidate


def _index_unique(
    items: list[dict],
    *,
    key: str,
) -> dict:
    """Index entries and reject duplicated identifiers."""

    if not isinstance(items, list) or not items:
        raise ValueError(f"Expected a non-empty list of {key}")

    indexed = {}

    for item in items:
        if not isinstance(item, dict) or key not in item:
            raise ValueError(f"Invalid entry: missing {key}")

        identifier = item[key]

        if (
            isinstance(identifier, bool)
            or not isinstance(identifier, (str, int))
            or (isinstance(identifier, str) and not identifier)
        ):
            raise ValueError(f"Invalid {key}: {identifier!r}")

        if identifier in indexed:
            raise ValueError(f"Duplicate {key}: {identifier}")

        indexed[identifier] = item

    return indexed


def _score(value: object, *, metric: str) -> float:
    """Validate normalized retrieval metric values."""

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(f"Invalid score for {metric}: {value!r}")

    return float(value)


def compare_retrieval_reports(
    *,
    baseline: dict,
    candidate: dict,
    allowed_drop: float = 0.0,
) -> tuple[RegressionFinding, ...]:
    """Compare the same dataset across retrieval implementations.

    Different embedding models and retrieval methods are allowed.
    Dataset identity, evaluation K values and case IDs must match.
    """

    if (
        isinstance(allowed_drop, bool)
        or not isinstance(allowed_drop, (int, float))
        or not isfinite(allowed_drop)
        or not 0 <= allowed_drop <= 1
    ):
        raise ValueError("allowed_drop must be between 0 and 1")

    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise TypeError("Reports must be JSON objects")

    for report in (baseline, candidate):
        version = report.get("schema_version")

        if type(version) is not int or version != 1:
            raise ValueError("Unsupported report schema version")

    for key in ("dataset_id", "dataset_version"):
        original = baseline.get(key)
        current = candidate.get(key)

        if (
            not isinstance(original, str)
            or not original.strip()
            or not isinstance(current, str)
            or not current.strip()
        ):
            raise ValueError(
                f"Missing or invalid report metadata: {key}"
            )

        if original != current:
            raise ValueError(f"Report mismatch: {key}")

    baseline_by_k = _index_unique(
        baseline.get("evaluations"),
        key="k",
    )
    candidate_by_k = _index_unique(
        candidate.get("evaluations"),
        key="k",
    )

    if baseline_by_k.keys() != candidate_by_k.keys():
        raise ValueError("Reports contain different K values")

    findings: list[RegressionFinding] = []

    for k in sorted(baseline_by_k):
        if not isinstance(k, int) or k <= 0:
            raise ValueError(f"Invalid K value: {k!r}")

        original = baseline_by_k[k]
        current = candidate_by_k[k]

        original_cases = _index_unique(
            original.get("cases"),
            key="case_id",
        )
        current_cases = _index_unique(
            current.get("cases"),
            key="case_id",
        )

        if original_cases.keys() != current_cases.keys():
            raise ValueError(
                f"Reports contain different case IDs at K={k}"
            )

        for metric in AGGREGATE_METRICS:
            before = _score(
                original.get(metric),
                metric=metric,
            )
            after = _score(
                current.get(metric),
                metric=metric,
            )

            if before - after > allowed_drop:
                findings.append(
                    RegressionFinding(
                        k=k,
                        case_id=None,
                        metric=metric,
                        baseline=before,
                        candidate=after,
                    )
                )

        for case_id in sorted(original_cases):
            old_case = original_cases[case_id]
            new_case = current_cases[case_id]

            for metric in QUERY_METRICS:
                before = _score(
                    old_case.get(metric),
                    metric=metric,
                )
                after = _score(
                    new_case.get(metric),
                    metric=metric,
                )

                if before - after > allowed_drop:
                    findings.append(
                        RegressionFinding(
                            k=k,
                            case_id=case_id,
                            metric=metric,
                            baseline=before,
                            candidate=after,
                        )
                    )

    return tuple(findings)
