"""Service orchestrating benchmark execution, trace sanitization, and comparisons (T260026)."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.embedding import EMBEDDING_MODEL_NAME
from app.evaluation.agent_dataset import (
    DEFAULT_SYNTHETIC_BENCHMARK_DATASET,
    BenchmarkCategory,
)
from app.evaluation.agent_metrics import BenchmarkAggregateReport
from app.evaluation.agent_runner import AgentBenchmarkRunner
from app.models.benchmark import AgentBenchmarkRun
from app.repositories import benchmark as bench_repo
from app.schemas.benchmark import (
    BenchmarkComparisonResponse,
    BenchmarkRunCreate,
    MetricDelta,
)

logger = logging.getLogger(__name__)


def sanitize_trace(raw_trace: dict[str, Any] | None) -> dict[str, Any]:
    """Sanitize execution trace to strip secrets, authorization tokens, and confidential keys."""
    if not raw_trace:
        return {}

    sanitized = dict(raw_trace)
    # Remove sensitive keys
    for key in ["authorization", "token", "password", "jwt_secret_key", "secret"]:
        sanitized.pop(key, None)

    # Sanitize steps
    sanitized_steps = []
    for step in sanitized.get("steps", []):
        st = dict(step)
        args = st.get("arguments")
        if isinstance(args, dict):
            st["arguments"] = {
                k: ("[REDACTED]" if any(s in k.lower() for s in ["token", "secret", "password"]) else v)
                for k, v in args.items()
            }
        sanitized_steps.append(st)
    sanitized["steps"] = sanitized_steps
    return sanitized


class BenchmarkService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory
        self.settings = get_settings()

    async def execute_and_record_run(
        self,
        *,
        workspace_id: UUID,
        created_by: UUID,
        request: BenchmarkRunCreate,
    ) -> AgentBenchmarkRun:
        """Run evaluation benchmark and persist run + individual case outcomes."""
        model_name = request.model_name or (
            self.settings.ollama_model if request.execution_mode == "real" else "scripted-mock-v1"
        )
        cat_filter = (
            BenchmarkCategory(request.category_filter)
            if request.category_filter
            else None
        )

        runtime_config = {
            "prompt_version": "v1.0",
            "agent_max_steps": self.settings.agent_max_steps,
            "agent_max_tool_calls": self.settings.agent_max_tool_calls,
            "agent_llm_timeout_seconds": self.settings.agent_llm_timeout_seconds,
            "agent_max_result_bytes": self.settings.agent_max_result_bytes,
        }

        # 1. Create run in running status
        async with self.session_factory() as session:
            run = await bench_repo.create_benchmark_run(
                session,
                workspace_id=workspace_id,
                created_by=created_by,
                name=request.name,
                dataset_id=request.dataset_id,
                dataset_version=DEFAULT_SYNTHETIC_BENCHMARK_DATASET.version,
                execution_mode=request.execution_mode,
                model_name=model_name,
                embedding_model=EMBEDDING_MODEL_NAME if request.execution_mode == "real" else "synthetic-384",
                runtime_config=runtime_config,
            )
            run_id = run.id

        # 2. Execute benchmark runner
        runner = AgentBenchmarkRunner(
            dataset=DEFAULT_SYNTHETIC_BENCHMARK_DATASET,
            model_name=model_name,
            execution_mode=request.execution_mode,
        )

        report: BenchmarkAggregateReport = await runner.run_benchmark(
            session_factory=self.session_factory,
            category_filter=cat_filter,
            test_user_id=created_by,
        )

        # 3. Persist individual case results
        async with self.session_factory() as session:
            for outcome in report.case_outcomes:
                await bench_repo.record_case_result(
                    session,
                    benchmark_run_id=run_id,
                    case_id=outcome.case_id,
                    case_name=outcome.case_name,
                    category=outcome.category.value,
                    is_adversarial=outcome.is_adversarial,
                    passed=outcome.passed,
                    failure_classification=outcome.failure_classification.value,
                    score=outcome.score,
                    reason=outcome.reason,
                    tool_accuracy=outcome.tool_accuracy,
                    citation_f1=outcome.citation_f1,
                    grounding_score=outcome.grounding_score,
                    latency_ms=outcome.latency_ms,
                    sanitized_trace=sanitize_trace(outcome.sanitized_trace),
                    metrics=outcome.metrics,
                )

            # 4. Finish benchmark run with aggregate summary
            category_scores_dict = {
                k: {
                    "total_cases": v.total_cases,
                    "passed_cases": v.passed_cases,
                    "success_rate": v.success_rate,
                    "avg_latency_ms": v.average_latency_ms,
                }
                for k, v in report.category_breakdown.items()
            }

            await bench_repo.finish_benchmark_run(
                session,
                run_id=run_id,
                status="completed",
                total_cases=report.total_cases,
                passed_cases=report.passed_cases,
                failed_cases=report.failed_cases,
                task_success_rate=report.task_success_rate,
                tool_call_accuracy=report.tool_call_accuracy,
                citation_f1=report.citation_f1,
                security_blocking_rate=report.security_attack_blocking_rate,
                benign_overblock_rate=report.benign_overblock_rate,
                latency_p50_ms=report.latency_p50_ms,
                latency_p95_ms=report.latency_p95_ms,
                latency_mean_ms=report.latency_mean_ms,
                failure_summary=report.failure_breakdown,
                category_scores=category_scores_dict,
            )
            # Re-fetch with eagerly loaded case_results
            loaded_run = await bench_repo.get_benchmark_run(session, run_id)

        return loaded_run  # type: ignore

    @staticmethod
    def compare_runs(
        current: AgentBenchmarkRun,
        baseline: AgentBenchmarkRun,
    ) -> BenchmarkComparisonResponse:
        """Calculate mathematical deltas between two benchmark runs."""
        def _delta(cur: float, base: float, higher_is_better: bool = True) -> MetricDelta:
            diff = round(cur - base, 4)
            improved = diff > 0 if higher_is_better else diff < 0
            return MetricDelta(
                current=round(cur, 4),
                baseline=round(base, 4),
                delta=diff,
                improved=improved,
            )

        task_acc_delta = _delta(current.task_success_rate, baseline.task_success_rate, True)
        tool_acc_delta = _delta(current.tool_call_accuracy, baseline.tool_call_accuracy, True)
        cite_f1_delta = _delta(current.citation_f1, baseline.citation_f1, True)
        lat_p50_delta = _delta(current.latency_p50_ms, baseline.latency_p50_ms, False)

        sec_delta = None
        if current.security_blocking_rate is not None and baseline.security_blocking_rate is not None:
            sec_delta = _delta(current.security_blocking_rate, baseline.security_blocking_rate, True)

        # Compare individual test cases
        cur_cases = {c.case_id: c.passed for c in current.case_results}
        base_cases = {c.case_id: c.passed for c in baseline.case_results}

        newly_failing = [
            cid for cid, base_passed in base_cases.items()
            if base_passed and not cur_cases.get(cid, False)
        ]
        newly_passing = [
            cid for cid, cur_passed in cur_cases.items()
            if cur_passed and not base_cases.get(cid, False)
        ]

        summary = (
            f"So sánh giữa {current.model_name} ({current.execution_mode}) và baseline {baseline.model_name} ({baseline.execution_mode}): "
            f"Tỷ lệ thành công {'tăng' if task_acc_delta.improved else 'giảm' if task_acc_delta.delta < 0 else 'không đổi'} {abs(task_acc_delta.delta) * 100:.1f}%. "
            f"Độ trễ P50 {'giảm' if lat_p50_delta.improved else 'tăng'} {abs(lat_p50_delta.delta):.0f}ms."
        )

        return BenchmarkComparisonResponse(
            current_run_id=current.id,
            baseline_run_id=baseline.id,
            current_model=current.model_name,
            baseline_model=baseline.model_name,
            current_mode=current.execution_mode,
            baseline_mode=baseline.execution_mode,
            task_success_rate=task_acc_delta,
            tool_call_accuracy=tool_acc_delta,
            citation_f1=cite_f1_delta,
            latency_p50_ms=lat_p50_delta,
            security_blocking_rate=sec_delta,
            newly_failing_cases=newly_failing,
            newly_passing_cases=newly_passing,
            summary=summary,
        )
