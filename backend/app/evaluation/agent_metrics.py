"""Mathematical definitions, aggregators, and metrics reporting for AI Agent Benchmarks (T260026).

Explicitly defines:
- Numerators and denominators for all metrics.
- Exclusions (e.g. excluding benign cases from security denominators to prevent vacuous scores).
- Latency P50 and P95 calculations.
- Failure classification breakdown.
"""

import math
from dataclasses import dataclass, field
from typing import Any

from app.evaluation.agent_dataset import BenchmarkCategory, FailureClassification
from app.evaluation.agent_evaluators import CaseEvaluationOutcome


def calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculate percentile using nearest-rank or linear interpolation."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(sorted_v[int(k)], 2)
    d0 = sorted_v[int(f)] * (c - k)
    d1 = sorted_v[int(c)] * (k - f)
    return round(d0 + d1, 2)


@dataclass(slots=True)
class CategorySummary:
    category: BenchmarkCategory
    total_cases: int
    passed_cases: int
    failed_cases: int
    success_rate: float
    average_latency_ms: float


@dataclass(slots=True)
class BenchmarkAggregateReport:
    """Consolidated benchmark metrics across all evaluated test cases."""

    dataset_id: str
    dataset_version: str
    model_name: str
    execution_mode: str  # "real" | "simulated"
    total_cases: int
    passed_cases: int
    failed_cases: int

    task_success_rate: float
    tool_call_accuracy: float
    citation_precision: float
    citation_recall: float
    citation_f1: float

    # Security metrics: strictly computed over adversarial attack attempts
    adversarial_attempts_count: int
    adversarial_blocked_count: int
    security_attack_blocking_rate: float | None

    # Benign metrics: false positives
    benign_tasks_count: int
    benign_overblocked_count: int
    benign_overblock_rate: float

    latency_p50_ms: float
    latency_p95_ms: float
    latency_mean_ms: float

    category_breakdown: dict[str, CategorySummary]
    failure_breakdown: dict[str, int]
    case_outcomes: list[CaseEvaluationOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "model_name": self.model_name,
            "execution_mode": self.execution_mode,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "task_success_rate": self.task_success_rate,
            "tool_call_accuracy": self.tool_call_accuracy,
            "citation_precision": self.citation_precision,
            "citation_recall": self.citation_recall,
            "citation_f1": self.citation_f1,
            "adversarial_attempts_count": self.adversarial_attempts_count,
            "adversarial_blocked_count": self.adversarial_blocked_count,
            "security_attack_blocking_rate": self.security_attack_blocking_rate,
            "benign_tasks_count": self.benign_tasks_count,
            "benign_overblocked_count": self.benign_overblocked_count,
            "benign_overblock_rate": self.benign_overblock_rate,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
            "latency_mean_ms": self.latency_mean_ms,
            "category_breakdown": {
                k: {
                    "category": v.category.value,
                    "total_cases": v.total_cases,
                    "passed_cases": v.passed_cases,
                    "failed_cases": v.failed_cases,
                    "success_rate": v.success_rate,
                    "average_latency_ms": v.average_latency_ms,
                }
                for k, v in self.category_breakdown.items()
            },
            "failure_breakdown": self.failure_breakdown,
            "cases": [
                {
                    "case_id": o.case_id,
                    "case_name": o.case_name,
                    "category": o.category.value,
                    "is_adversarial": o.is_adversarial,
                    "passed": o.passed,
                    "failure_classification": o.failure_classification.value,
                    "score": o.score,
                    "reason": o.reason,
                    "latency_ms": o.latency_ms,
                }
                for o in self.case_outcomes
            ],
        }


def compute_benchmark_metrics(
    *,
    dataset_id: str,
    dataset_version: str,
    model_name: str,
    execution_mode: str,
    outcomes: list[CaseEvaluationOutcome],
) -> BenchmarkAggregateReport:
    """Compute aggregate benchmark metrics from individual case outcomes."""
    total_cases = len(outcomes)
    if total_cases == 0:
        return BenchmarkAggregateReport(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            model_name=model_name,
            execution_mode=execution_mode,
            total_cases=0,
            passed_cases=0,
            failed_cases=0,
            task_success_rate=0.0,
            tool_call_accuracy=0.0,
            citation_precision=0.0,
            citation_recall=0.0,
            citation_f1=0.0,
            adversarial_attempts_count=0,
            adversarial_blocked_count=0,
            security_attack_blocking_rate=None,
            benign_tasks_count=0,
            benign_overblocked_count=0,
            benign_overblock_rate=0.0,
            latency_p50_ms=0.0,
            latency_p95_ms=0.0,
            latency_mean_ms=0.0,
            category_breakdown={},
            failure_breakdown={},
            case_outcomes=[],
        )

    passed_cases = sum(1 for o in outcomes if o.passed)
    failed_cases = total_cases - passed_cases
    task_success_rate = round(passed_cases / total_cases, 4)

    # Tool accuracy across benign tasks where tools were evaluated
    tool_scores = [o.tool_accuracy for o in outcomes if not o.is_adversarial]
    tool_call_accuracy = (
        round(sum(tool_scores) / len(tool_scores), 4) if tool_scores else 1.0
    )

    # Citation quality across non-adversarial cases
    cite_cases = [o for o in outcomes if not o.is_adversarial]
    citation_precision = (
        round(sum(c.citation_precision for c in cite_cases) / len(cite_cases), 4)
        if cite_cases
        else 1.0
    )
    citation_recall = (
        round(sum(c.citation_recall for c in cite_cases) / len(cite_cases), 4)
        if cite_cases
        else 1.0
    )
    citation_f1 = (
        round(sum(c.citation_f1 for c in cite_cases) / len(cite_cases), 4)
        if cite_cases
        else 1.0
    )

    # Security Attack Blocking Rate: ONLY computed over adversarial attack attempts
    adversarial_cases = [o for o in outcomes if o.is_adversarial]
    adv_count = len(adversarial_cases)
    adv_blocked = sum(1 for o in adversarial_cases if o.security_attack_blocked)
    security_blocking_rate = (
        round(adv_blocked / adv_count, 4) if adv_count > 0 else None
    )

    # Benign Over-blocking Rate
    benign_cases = [o for o in outcomes if not o.is_adversarial]
    benign_count = len(benign_cases)
    benign_overblocked = sum(1 for o in benign_cases if o.benign_overblocked)
    benign_overblock_rate = (
        round(benign_overblocked / benign_count, 4) if benign_count > 0 else 0.0
    )

    # Latencies
    latencies = [o.latency_ms for o in outcomes]
    latency_p50 = calculate_percentile(latencies, 50.0)
    latency_p95 = calculate_percentile(latencies, 95.0)
    latency_mean = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    # Category breakdown
    category_map: dict[str, list[CaseEvaluationOutcome]] = {}
    for o in outcomes:
        category_map.setdefault(o.category.value, []).append(o)

    cat_breakdown: dict[str, CategorySummary] = {}
    for cat_name, cat_outcomes in category_map.items():
        cat_total = len(cat_outcomes)
        cat_passed = sum(1 for o in cat_outcomes if o.passed)
        cat_latencies = [o.latency_ms for o in cat_outcomes]
        cat_breakdown[cat_name] = CategorySummary(
            category=BenchmarkCategory(cat_name),
            total_cases=cat_total,
            passed_cases=cat_passed,
            failed_cases=cat_total - cat_passed,
            success_rate=round(cat_passed / cat_total, 4) if cat_total > 0 else 0.0,
            average_latency_ms=round(sum(cat_latencies) / len(cat_latencies), 2) if cat_latencies else 0.0,
        )

    # Failure breakdown
    failure_breakdown: dict[str, int] = {
        fc.value: 0 for fc in FailureClassification if fc != FailureClassification.NONE
    }
    for o in outcomes:
        if not o.passed and o.failure_classification != FailureClassification.NONE:
            failure_breakdown[o.failure_classification.value] += 1

    return BenchmarkAggregateReport(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        model_name=model_name,
        execution_mode=execution_mode,
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        task_success_rate=task_success_rate,
        tool_call_accuracy=tool_call_accuracy,
        citation_precision=citation_precision,
        citation_recall=citation_recall,
        citation_f1=citation_f1,
        adversarial_attempts_count=adv_count,
        adversarial_blocked_count=adv_blocked,
        security_attack_blocking_rate=security_blocking_rate,
        benign_tasks_count=benign_count,
        benign_overblocked_count=benign_overblocked,
        benign_overblock_rate=benign_overblock_rate,
        latency_p50_ms=latency_p50,
        latency_p95_ms=latency_p95,
        latency_mean_ms=latency_mean,
        category_breakdown=cat_breakdown,
        failure_breakdown=failure_breakdown,
        case_outcomes=outcomes,
    )
