"""Database repository for Agent Reliability Benchmarks (T260026)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.benchmark import AgentBenchmarkCaseResult, AgentBenchmarkRun


async def create_benchmark_run(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    created_by: UUID,
    name: str,
    dataset_id: str,
    dataset_version: str,
    execution_mode: str,
    model_name: str,
    embedding_model: str | None,
    runtime_config: dict[str, Any],
) -> AgentBenchmarkRun:
    run = AgentBenchmarkRun(
        id=uuid4(),
        workspace_id=workspace_id,
        created_by=created_by,
        name=name,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        execution_mode=execution_mode,
        model_name=model_name,
        embedding_model=embedding_model,
        runtime_config=runtime_config,
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def record_case_result(
    session: AsyncSession,
    *,
    benchmark_run_id: UUID,
    case_id: str,
    case_name: str,
    category: str,
    is_adversarial: bool,
    passed: bool,
    failure_classification: str,
    score: float,
    reason: str,
    tool_accuracy: float,
    citation_f1: float,
    grounding_score: float,
    latency_ms: float,
    sanitized_trace: dict[str, Any] | None,
    metrics: dict[str, Any] | None,
) -> AgentBenchmarkCaseResult:
    case_result = AgentBenchmarkCaseResult(
        id=uuid4(),
        benchmark_run_id=benchmark_run_id,
        case_id=case_id,
        case_name=case_name,
        category=category,
        is_adversarial=is_adversarial,
        passed=passed,
        failure_classification=failure_classification,
        score=score,
        reason=reason,
        tool_accuracy=tool_accuracy,
        citation_f1=citation_f1,
        grounding_score=grounding_score,
        latency_ms=latency_ms,
        sanitized_trace=sanitized_trace,
        metrics=metrics,
    )
    session.add(case_result)
    await session.commit()
    return case_result


async def finish_benchmark_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    status: str,
    total_cases: int,
    passed_cases: int,
    failed_cases: int,
    task_success_rate: float,
    tool_call_accuracy: float,
    citation_f1: float,
    security_blocking_rate: float | None,
    benign_overblock_rate: float,
    latency_p50_ms: float,
    latency_p95_ms: float,
    latency_mean_ms: float,
    failure_summary: dict[str, Any] | None,
    category_scores: dict[str, Any] | None,
) -> AgentBenchmarkRun | None:
    run = await session.get(AgentBenchmarkRun, run_id)
    if not run:
        return None

    run.status = status
    run.total_cases = total_cases
    run.passed_cases = passed_cases
    run.failed_cases = failed_cases
    run.task_success_rate = task_success_rate
    run.tool_call_accuracy = tool_call_accuracy
    run.citation_f1 = citation_f1
    run.security_blocking_rate = security_blocking_rate
    run.benign_overblock_rate = benign_overblock_rate
    run.latency_p50_ms = latency_p50_ms
    run.latency_p95_ms = latency_p95_ms
    run.latency_mean_ms = latency_mean_ms
    run.failure_summary = failure_summary
    run.category_scores = category_scores
    run.completed_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(run)
    return run


async def list_benchmark_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentBenchmarkRun], int]:
    count_stmt = select(func.count(AgentBenchmarkRun.id)).where(
        AgentBenchmarkRun.workspace_id == workspace_id
    )
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(AgentBenchmarkRun)
        .where(AgentBenchmarkRun.workspace_id == workspace_id)
        .order_by(desc(AgentBenchmarkRun.created_at))
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    runs = list(result.scalars().all())
    return runs, total


async def get_benchmark_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    workspace_id: UUID | None = None,
) -> AgentBenchmarkRun | None:
    stmt = (
        select(AgentBenchmarkRun)
        .where(AgentBenchmarkRun.id == run_id)
        .options(selectinload(AgentBenchmarkRun.case_results))
    )
    if workspace_id is not None:
        stmt = stmt.where(AgentBenchmarkRun.workspace_id == workspace_id)

    result = await session.execute(stmt)
    return result.scalar_one_or_none()
