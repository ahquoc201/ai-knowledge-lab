"""CLI Evaluation Runner for Governed AI Agent Runtime (T260026).

Usage:
    python -m app.evaluation.agent_cli --mode simulated
    python -m app.evaluation.agent_cli --mode real --model qwen3:1.7b --output-json report.json
    python -m app.evaluation.agent_cli --compare-with baseline.json
"""

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.evaluation.agent_dataset import (
    DEFAULT_SYNTHETIC_BENCHMARK_DATASET,
    BenchmarkCategory,
)
from app.evaluation.agent_metrics import BenchmarkAggregateReport
from app.evaluation.agent_runner import AgentBenchmarkRunner
from app.repositories.user import create_user


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run reproducible AI Agent & RAG reliability benchmarks."
    )
    parser.add_argument(
        "--mode",
        choices=["simulated", "real"],
        default="simulated",
        help="Execution mode: 'simulated' (offline fixtures) or 'real' (live Ollama model)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model identifier (default: current configured Ollama model or simulated fixture)",
    )
    parser.add_argument(
        "--category",
        choices=[c.value for c in BenchmarkCategory],
        default=None,
        help="Filter evaluation to a specific benchmark category",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Output JSON report file path",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Output CSV summary file path",
    )
    parser.add_argument(
        "--compare-with",
        type=Path,
        default=None,
        help="Path to an existing JSON report to compare against and report delta",
    )
    return parser.parse_args()


def export_csv_report(report: BenchmarkAggregateReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Case ID",
            "Case Name",
            "Category",
            "Adversarial",
            "Passed",
            "Classification",
            "Score",
            "Tool Accuracy",
            "Citation F1",
            "Grounding Score",
            "Latency (ms)",
            "Reason",
        ])
        for o in report.case_outcomes:
            writer.writerow([
                o.case_id,
                o.case_name,
                o.category.value,
                o.is_adversarial,
                o.passed,
                o.failure_classification.value,
                o.score,
                o.tool_accuracy,
                o.citation_f1,
                o.grounding_score,
                o.latency_ms,
                o.reason,
            ])


def print_comparison(current: BenchmarkAggregateReport, baseline_data: dict) -> None:
    print("\n" + "=" * 70)
    print("HISTORICAL BENCHMARK COMPARISON")
    print("=" * 70)
    cur_acc = current.task_success_rate * 100
    base_acc = baseline_data.get("task_success_rate", 0.0) * 100
    delta_acc = cur_acc - base_acc

    cur_p50 = current.latency_p50_ms
    base_p50 = baseline_data.get("latency_p50_ms", 0.0)
    delta_p50 = cur_p50 - base_p50

    cur_tool = current.tool_call_accuracy * 100
    base_tool = baseline_data.get("tool_call_accuracy", 0.0) * 100
    delta_tool = cur_tool - base_tool

    cur_sec = current.security_attack_blocking_rate
    base_sec = baseline_data.get("security_attack_blocking_rate")

    print(f"Dataset: {current.dataset_id} ({current.dataset_version})")
    print(f"Current Model : {current.model_name} ({current.execution_mode})")
    print(f"Baseline Model: {baseline_data.get('model_name')} ({baseline_data.get('execution_mode')})")
    print("-" * 70)
    print(f"Task Success Rate : {cur_acc:.1f}% vs {base_acc:.1f}% (Delta: {delta_acc:+.1f}%)")
    print(f"Tool Call Accuracy: {cur_tool:.1f}% vs {base_tool:.1f}% (Delta: {delta_tool:+.1f}%)")
    if cur_sec is not None and base_sec is not None:
        delta_sec = (cur_sec * 100) - (base_sec * 100)
        print(f"Security Blocking : {cur_sec*100:.1f}% vs {base_sec*100:.1f}% (Delta: {delta_sec:+.1f}%)")
    print(f"Latency P50       : {cur_p50:.1f}ms vs {base_p50:.1f}ms (Delta: {delta_p50:+.1f}ms)")
    print("=" * 70)


def print_terminal_summary(report: BenchmarkAggregateReport) -> None:
    print("\n" + "=" * 75)
    print(f"AGENT RELIABILITY BENCHMARK REPORT: {report.dataset_id} v{report.dataset_version}")
    print(f"Execution Mode: {report.execution_mode.upper()} | Model: {report.model_name}")
    print("=" * 75)

    print(f"\n--- OVERALL METRICS (Total Cases: {report.total_cases}) ---")
    print(f"Task Success Rate          : {report.task_success_rate * 100:.1f}% ({report.passed_cases}/{report.total_cases})")
    print(f"Tool Selection Accuracy    : {report.tool_call_accuracy * 100:.1f}%")
    print(f"Citation Precision / Recall: {report.citation_precision:.2f} / {report.citation_recall:.2f} (Reference F1: {report.citation_f1:.2f})")

    # Phase B: Detailed Security Disaggregation
    inj_rate_str = f"{report.prompt_injection_resistance_rate * 100:.1f}%" if report.prompt_injection_resistance_rate is not None else "N/A"
    print(f"Prompt Injection Resistance: {inj_rate_str}")
    print(f"Unauthorized Tool Attempts : {report.unauthorized_tool_attempt_rate * 100:.1f}%")

    if report.backend_policy_blocking_effectiveness is not None:
        print(f"Policy Blocking Effective  : {report.backend_policy_blocking_effectiveness * 100:.1f}%")
    else:
        print("Policy Blocking Effective  : N/A (no unauthorized tools were attempted)")

    print(f"Actual Data Leakage Rate   : {report.actual_data_leakage_rate * 100:.1f}%")

    tenant_rate_str = f"{report.tenant_isolation_success_rate * 100:.1f}%" if report.tenant_isolation_success_rate is not None else "N/A"
    print(f"Tenant Isolation Success   : {tenant_rate_str}")

    if report.security_attack_blocking_rate is not None:
        print(
            f"Adversarial Defense Block  : {report.security_attack_blocking_rate * 100:.1f}% "
            f"({report.adversarial_blocked_count}/{report.adversarial_attempts_count} attacks blocked)"
        )
    else:
        print("Adversarial Defense Block  : N/A (no adversarial attacks in selection)")

    print(
        f"Benign Over-blocking (FP)  : {report.benign_overblock_rate * 100:.1f}% "
        f"({report.benign_overblocked_count}/{report.benign_tasks_count} benign requests)"
    )

    print(f"Latency P50 / P95 / Mean   : {report.latency_p50_ms}ms / {report.latency_p95_ms}ms / {report.latency_mean_ms}ms")

    print("\n--- CATEGORY BREAKDOWN ---")
    print(f"{'Category':<32} | {'Cases':<6} | {'Passed':<6} | {'Pass Rate':<10} | {'Avg Latency'}")
    print("-" * 75)
    for cat_name, sumry in report.category_breakdown.items():
        print(
            f"{cat_name:<32} | {sumry.total_cases:<6} | {sumry.passed_cases:<6} | "
            f"{sumry.success_rate * 100:>6.1f}%   | {sumry.average_latency_ms:>7.1f}ms"
        )

    print("\n--- INDIVIDUAL TEST CASES ---")
    for o in report.case_outcomes:
        badge = "[PASS]" if o.passed else "[FAIL]"
        adv = " (Adversarial)" if o.is_adversarial else ""
        print(f"  {badge} {o.case_id}: {o.case_name}{adv} - {o.reason} ({o.latency_ms}ms)")

    if report.failed_cases > 0:
        print("\n--- FAILURE SUMMARY ---")
        for ftype, count in report.failure_breakdown.items():
            if count > 0:
                print(f"  - {ftype}: {count}")

    print("=" * 75 + "\n")


async def async_main() -> int:
    args = parse_args()
    settings = get_settings()

    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Provision a clean benchmark runner user
    async with session_factory() as session:
        bench_email = f"benchmark_runner_{uuid4().hex[:6]}@example.com"
        user = await create_user(
            session,
            email=bench_email,
            hashed_password="bench_pwd_hash",
            full_name="Benchmark Runner Service",
        )
        user_id = user.id

    category_filter = BenchmarkCategory(args.category) if args.category else None
    runner = AgentBenchmarkRunner(
        dataset=DEFAULT_SYNTHETIC_BENCHMARK_DATASET,
        model_name=args.model,
        execution_mode=args.mode,
    )

    report = await runner.run_benchmark(
        session_factory=session_factory,
        category_filter=category_filter,
        test_user_id=user_id,
    )

    print_terminal_summary(report)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[+] Saved JSON report to {args.output_json}")

    if args.output_csv:
        export_csv_report(report, args.output_csv)
        print(f"[+] Saved CSV report to {args.output_csv}")

    if args.compare_with and args.compare_with.exists():
        baseline_data = json.loads(args.compare_with.read_text(encoding="utf-8"))
        print_comparison(report, baseline_data)

    await engine.dispose()
    return 0 if report.failed_cases == 0 else 1


def main() -> None:
    code = asyncio.run(async_main())
    sys.exit(code)


if __name__ == "__main__":
    main()
