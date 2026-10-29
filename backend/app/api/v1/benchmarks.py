"""API endpoints for Agent Reliability Benchmarks & Evaluation (T260026)."""

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_session,
    require_workspace_permission,
)
from app.core.workspace_role import WorkspacePermission
from app.db.session import AsyncSessionLocal
from app.evaluation.agent_dataset import (
    DEFAULT_SYNTHETIC_BENCHMARK_DATASET,
    BenchmarkCategory,
)
from app.models.user import User
from app.models.workspace_membership import WorkspaceMembership
from app.repositories import benchmark as bench_repo
from app.schemas.benchmark import (
    BenchmarkComparisonResponse,
    BenchmarkRunCreate,
    BenchmarkRunListResponse,
    BenchmarkRunResponse,
    BenchmarkRunSummary,
)
from app.services.benchmark_service import BenchmarkService

router = APIRouter(
    prefix="/benchmarks",
    tags=["Agent Benchmarks"],
)


@router.get(
    "/datasets",
    response_model=dict,
)
async def get_benchmark_datasets(
    _current_user: Annotated[User, Depends(get_current_user)],
):
    """List available benchmark datasets and categories."""
    return {
        "datasets": [
            {
                "id": DEFAULT_SYNTHETIC_BENCHMARK_DATASET.dataset_id,
                "version": DEFAULT_SYNTHETIC_BENCHMARK_DATASET.version,
                "description": DEFAULT_SYNTHETIC_BENCHMARK_DATASET.description,
                "total_cases": len(DEFAULT_SYNTHETIC_BENCHMARK_DATASET.cases),
                "categories": [c.value for c in BenchmarkCategory],
            }
        ]
    }


@router.get(
    "/runs",
    response_model=BenchmarkRunListResponse,
)
async def list_benchmark_runs(
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.WORKSPACE_READ)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> BenchmarkRunListResponse:
    """List benchmark runs for the current workspace."""
    runs, total = await bench_repo.list_benchmark_runs(
        session,
        workspace_id=membership.workspace_id,
        limit=limit,
        offset=offset,
    )
    return BenchmarkRunListResponse(
        items=[BenchmarkRunSummary.model_validate(r) for r in runs],
        total=total,
    )


@router.post(
    "/runs",
    response_model=BenchmarkRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_benchmark_run(
    data: BenchmarkRunCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.WORKSPACE_UPDATE)),
    ],
) -> BenchmarkRunResponse:
    """Trigger a new benchmark run in the workspace."""
    service = BenchmarkService(AsyncSessionLocal)
    run = await service.execute_and_record_run(
        workspace_id=membership.workspace_id,
        created_by=current_user.id,
        request=data,
    )
    return BenchmarkRunResponse.model_validate(run)


@router.get(
    "/runs/{run_id}",
    response_model=BenchmarkRunResponse,
)
async def get_benchmark_run_detail(
    run_id: UUID,
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.WORKSPACE_READ)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BenchmarkRunResponse:
    """Get full details and individual test case results for a benchmark run."""
    run = await bench_repo.get_benchmark_run(
        session,
        run_id,
        workspace_id=membership.workspace_id,
    )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benchmark run not found in workspace",
        )
    return BenchmarkRunResponse.model_validate(run)


@router.get(
    "/runs/{run_id}/compare/{baseline_id}",
    response_model=BenchmarkComparisonResponse,
)
async def compare_benchmark_runs(
    run_id: UUID,
    baseline_id: UUID,
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.WORKSPACE_READ)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BenchmarkComparisonResponse:
    """Compare two benchmark runs in the workspace and compute metrics deltas."""
    cur_run = await bench_repo.get_benchmark_run(
        session, run_id, workspace_id=membership.workspace_id
    )
    if not cur_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current benchmark run not found in workspace",
        )

    base_run = await bench_repo.get_benchmark_run(
        session, baseline_id, workspace_id=membership.workspace_id
    )
    if not base_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Baseline benchmark run not found in workspace",
        )

    return BenchmarkService.compare_runs(current=cur_run, baseline=base_run)
