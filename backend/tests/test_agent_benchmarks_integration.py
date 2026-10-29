"""Integration tests for Benchmark persistence, execution, and comparisons (T260026 - Slice B)."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.workspace_role import WorkspaceRole
from app.evaluation.agent_dataset import BenchmarkCategory
from app.models.benchmark import AgentBenchmarkCaseResult, AgentBenchmarkRun
from app.repositories import benchmark as bench_repo
from app.repositories.user import create_user
from app.repositories.workspace import create_workspace
from app.repositories.workspace_membership import create_membership
from app.schemas.benchmark import BenchmarkRunCreate
from app.services.benchmark_service import BenchmarkService, sanitize_trace


@pytest.fixture
def session_factory():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory


@pytest.mark.anyio
async def test_sanitize_trace():
    """Verify trace sanitizer strips authentication secrets and redacts argument tokens."""
    dirty_trace = {
        "authorization": "Bearer secret_token_12345",
        "password": "Password123!",
        "goal": "Normal user goal",
        "steps": [
            {
                "tool_name": "search_workspace_documents",
                "arguments": {"query": "test query", "user_token": "secret_abc"},
            }
        ],
    }
    clean = sanitize_trace(dirty_trace)
    assert "authorization" not in clean
    assert "password" not in clean
    assert clean["goal"] == "Normal user goal"
    assert clean["steps"][0]["arguments"]["user_token"] == "[REDACTED]"
    assert clean["steps"][0]["arguments"]["query"] == "test query"


@pytest.mark.anyio
async def test_execute_and_persist_benchmark_run(session_factory):
    """Verify executing and recording a benchmark run persists all data into PostgreSQL."""
    async with session_factory() as session:
        # 1. Setup user and workspace
        user = await create_user(
            session,
            email=f"bench_int_{uuid4().hex[:6]}@example.com",
            hashed_password="hash",
            full_name="Bench Tester",
        )
        ws = await create_workspace(
            session,
            name=f"Bench Test WS {uuid4().hex[:4]}",
            slug=f"bench-ws-{uuid4().hex[:6]}",
            created_by=user.id,
        )
        await create_membership(
            session,
            workspace_id=ws.id,
            user_id=user.id,
            role=WorkspaceRole.OWNER,
        )
        ws_id = ws.id
        user_id = user.id

    service = BenchmarkService(session_factory)
    req = BenchmarkRunCreate(
        name="Slice B Verification Run",
        execution_mode="simulated",
        category_filter=BenchmarkCategory.RETRIEVAL_FACTUAL.value,
    )

    # Execute benchmark run for retrieval_factual (2 cases)
    run = await service.execute_and_record_run(
        workspace_id=ws_id,
        created_by=user_id,
        request=req,
    )

    assert run is not None
    assert run.status == "completed"
    assert run.total_cases == 2
    assert run.passed_cases == 2
    assert run.failed_cases == 0
    assert run.task_success_rate == 1.0

    # Read back from database
    async with session_factory() as session:
        retrieved_run = await bench_repo.get_benchmark_run(
            session, run.id, workspace_id=ws_id
        )
        assert retrieved_run is not None
        assert len(retrieved_run.case_results) == 2
        for case in retrieved_run.case_results:
            assert case.passed is True
            assert case.category == BenchmarkCategory.RETRIEVAL_FACTUAL.value
            assert case.latency_ms > 0

        # Test listing runs
        runs_list, total = await bench_repo.list_benchmark_runs(
            session, workspace_id=ws_id, limit=10
        )
        assert total >= 1
        assert any(r.id == run.id for r in runs_list)


@pytest.mark.anyio
async def test_compare_benchmark_runs():
    """Verify comparison logic accurately computes mathematical deltas and case differences."""
    run_id_1 = uuid4()
    run_id_2 = uuid4()

    run1 = AgentBenchmarkRun(
        id=run_id_1,
        workspace_id=uuid4(),
        created_by=uuid4(),
        name="Baseline",
        dataset_id="core",
        dataset_version="1.0",
        execution_mode="simulated",
        model_name="mock-v1",
        runtime_config={},
        status="completed",
        total_cases=2,
        passed_cases=2,
        failed_cases=0,
        task_success_rate=1.0,
        tool_call_accuracy=1.0,
        citation_f1=0.90,
        security_blocking_rate=1.0,
        benign_overblock_rate=0.0,
        latency_p50_ms=200.0,
        latency_p95_ms=300.0,
        latency_mean_ms=210.0,
        case_results=[
            AgentBenchmarkCaseResult(
                id=uuid4(),
                benchmark_run_id=run_id_1,
                case_id="C1",
                case_name="Case 1",
                category="retrieval_factual",
                passed=True,
                failure_classification="none",
                score=1.0,
                reason="OK",
                latency_ms=200.0,
            ),
            AgentBenchmarkCaseResult(
                id=uuid4(),
                benchmark_run_id=run_id_1,
                case_id="C2",
                case_name="Case 2",
                category="retrieval_factual",
                passed=True,
                failure_classification="none",
                score=1.0,
                reason="OK",
                latency_ms=210.0,
            ),
        ],
    )

    run2 = AgentBenchmarkRun(
        id=run_id_2,
        workspace_id=uuid4(),
        created_by=uuid4(),
        name="New Run",
        dataset_id="core",
        dataset_version="1.0",
        execution_mode="real",
        model_name="qwen3:1.7b",
        runtime_config={},
        status="completed",
        total_cases=2,
        passed_cases=1,
        failed_cases=1,
        task_success_rate=0.50,
        tool_call_accuracy=0.80,
        citation_f1=0.80,
        security_blocking_rate=1.0,
        benign_overblock_rate=0.0,
        latency_p50_ms=350.0,
        latency_p95_ms=500.0,
        latency_mean_ms=360.0,
        case_results=[
            AgentBenchmarkCaseResult(
                id=uuid4(),
                benchmark_run_id=run_id_2,
                case_id="C1",
                case_name="Case 1",
                category="retrieval_factual",
                passed=True,
                failure_classification="none",
                score=1.0,
                reason="OK",
                latency_ms=350.0,
            ),
            AgentBenchmarkCaseResult(
                id=uuid4(),
                benchmark_run_id=run_id_2,
                case_id="C2",
                case_name="Case 2",
                category="retrieval_factual",
                passed=False,
                failure_classification="grounding_failure",
                score=0.4,
                reason="Failed",
                latency_ms=360.0,
            ),
        ],
    )

    comparison = BenchmarkService.compare_runs(current=run2, baseline=run1)
    assert comparison.current_run_id == run_id_2
    assert comparison.baseline_run_id == run_id_1
    assert comparison.task_success_rate.delta == -0.50
    assert comparison.task_success_rate.improved is False
    assert comparison.latency_p50_ms.delta == 150.0
    assert comparison.latency_p50_ms.improved is False  # Higher latency is worse
    assert "C2" in comparison.newly_failing_cases
    assert len(comparison.newly_passing_cases) == 0
