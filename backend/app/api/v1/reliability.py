"""API endpoints for Reliability, Runtime Metrics & Recovery (T260028)."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_workspace_membership
from app.core.agent_state import AgentRunStatus
from app.models.agent import AgentRun
from app.models.user import User
from app.models.workspace_membership import WorkspaceMembership
from app.repositories import agent as agent_repo
from app.services.agent_recovery import AgentRecoveryService
from app.services.inference_governor import get_inference_governor
from app.services.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/reliability",
    tags=["Reliability & Operations"],
)


def _ensure_admin_or_owner(membership: WorkspaceMembership) -> None:
    role_str = str(membership.role).lower()
    if role_str not in ["owner", "admin", "workspacerole.owner", "workspacerole.admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace OWNER or ADMIN can access operational reliability tools",
        )


@router.get("/metrics")
async def get_reliability_metrics(
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[WorkspaceMembership, Depends(get_workspace_membership)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Retrieve runtime resource metrics, queue states, governor capacity and stuck runs."""
    _ensure_admin_or_owner(membership)

    now = datetime.now(UTC)

    # 1. Agent run counts in current workspace
    active_runs_q = await session.execute(
        select(func.count(AgentRun.id)).where(
            AgentRun.workspace_id == membership.workspace_id,
            AgentRun.status == AgentRunStatus.RUNNING.value,
        )
    )
    active_runs_count = active_runs_q.scalar_one()

    queued_runs_q = await session.execute(
        select(func.count(AgentRun.id)).where(
            AgentRun.workspace_id == membership.workspace_id,
            AgentRun.status == AgentRunStatus.CREATED.value,
        )
    )
    queued_runs_count = queued_runs_q.scalar_one()

    # 2. Stuck runs check
    stuck_runs = await agent_repo.list_stuck_runs(session, now)
    ws_stuck_runs = [r for r in stuck_runs if r.workspace_id == membership.workspace_id]

    # 3. Inference Governor metrics
    governor = get_inference_governor()
    gov_metrics = governor.metrics

    # 4. Rate Limiter status
    limiter = get_rate_limiter()

    return {
        "workspace_id": str(membership.workspace_id),
        "timestamp": now.isoformat(),
        "agent_runtime": {
            "active_runs": active_runs_count,
            "queued_runs": queued_runs_count,
            "stuck_runs_count": len(ws_stuck_runs),
            "stuck_runs": [
                {
                    "run_id": str(r.id),
                    "goal": r.goal[:60],
                    "status": r.status,
                    "lease_expires_at": r.lease_expires_at.isoformat() if r.lease_expires_at else None,
                    "recovery_attempts": r.recovery_attempts,
                }
                for r in ws_stuck_runs
            ],
        },
        "inference_governor": {
            "active_inferences": gov_metrics.active_inferences,
            "queued_requests": gov_metrics.queued_requests,
            "total_admitted": gov_metrics.total_admitted,
            "total_rejected": gov_metrics.total_rejected,
            "total_timeouts": gov_metrics.total_timeouts,
            "max_concurrency": gov_metrics.max_concurrency,
            "max_queue_size": gov_metrics.max_queue_size,
        },
        "rate_limiting": {
            "redis_connected": limiter.is_redis_active(),
            "mode": "distributed_redis" if limiter.is_redis_active() else "in_memory_fallback",
        },
    }


@router.post("/recover-stuck")
async def trigger_stuck_recovery(
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[WorkspaceMembership, Depends(get_workspace_membership)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Scan and recover stuck agent runs across the workspace."""
    _ensure_admin_or_owner(membership)

    recovery_svc = AgentRecoveryService()
    recovered = await recovery_svc.scan_and_recover_stuck_runs(
        session, workspace_id=membership.workspace_id
    )

    # Filter to current workspace for audit response
    return {
        "workspace_id": str(membership.workspace_id),
        "recovered_count": len(recovered),
        "recovered_runs": recovered,
    }
