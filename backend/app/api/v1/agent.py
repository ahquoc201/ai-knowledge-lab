"""API endpoints for Governed AI Agent Runtime."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_session,
    require_workspace_permission,
)
from app.core.agent_state import AgentRunStatus
from app.core.config import get_settings
from app.core.workspace_role import WorkspacePermission
from app.db.session import AsyncSessionLocal
from app.llm.base import LLMProvider
from app.llm.ollama import get_ollama_llm_provider
from app.models.agent import AgentRun
from app.models.user import User
from app.models.workspace_membership import WorkspaceMembership
from app.repositories import agent as agent_repo
from app.schemas.agent import (
    AgentApprovalResponse,
    AgentEventResponse,
    AgentRunCreate,
    AgentRunListResponse,
    AgentRunResponse,
    AgentStepResponse,
    ApprovalDecisionRequest,
)
from app.services.agent_approval import AgentApprovalService, ApprovalError
from app.services.agent_executor import ToolExecutor
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.agent_policy import AgentPolicy
from app.services.agent_tools import ToolRegistry, build_default_registry

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agent",
    tags=["Agent Runtime"],
)


def get_tool_registry() -> ToolRegistry:
    return build_default_registry()


def get_agent_orchestrator(
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
    llm_provider: Annotated[LLMProvider, Depends(get_ollama_llm_provider)],
) -> AgentOrchestrator:
    settings = get_settings()
    policy = AgentPolicy()
    executor = ToolExecutor(policy=policy, max_result_bytes=settings.agent_max_result_bytes)
    approval_service = AgentApprovalService(registry=registry, executor=executor)
    return AgentOrchestrator(
        registry=registry,
        executor=executor,
        approval_service=approval_service,
        llm_provider=llm_provider,
    )


async def _build_run_response(session: AsyncSession, run: AgentRun) -> AgentRunResponse:
    steps = await agent_repo.list_steps(session, run.id)
    step_responses = [AgentStepResponse.model_validate(s) for s in steps]

    pending_approval = await agent_repo.get_pending_approval_for_run(session, run.id)
    approval_response = (
        AgentApprovalResponse.model_validate(pending_approval)
        if pending_approval
        else None
    )

    resp = AgentRunResponse.model_validate(run)
    resp.steps = step_responses
    resp.pending_approval = approval_response
    return resp


@router.post(
    "/runs",
    response_model=AgentRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_run(
    data: AgentRunCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.WORKSPACE_READ)),
    ],
    orchestrator: Annotated[AgentOrchestrator, Depends(get_agent_orchestrator)],
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
    session: Annotated[AsyncSession, Depends(get_session)],
    background_tasks: BackgroundTasks,
    blocking: bool = Query(
        default=True,
        description="Whether to execute until first pause/completion before responding",
    ),
) -> AgentRunResponse:
    settings = get_settings()

    # Enforce active runs budget per user in this workspace
    active_count = await agent_repo.count_active_runs(
        session,
        workspace_id=membership.workspace_id,
        initiated_by=current_user.id,
    )
    if active_count >= settings.agent_max_active_runs_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Active agent run limit reached ({settings.agent_max_active_runs_per_user})",
        )

    # Determine allowed tools
    available_tools = registry.names()
    if data.allowed_tools:
        invalid = set(data.allowed_tools) - set(available_tools)
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown tools requested: {sorted(invalid)}",
            )
        allowed_tools = data.allowed_tools
    else:
        allowed_tools = available_tools

    run = await agent_repo.create_run(
        session,
        workspace_id=membership.workspace_id,
        initiated_by=current_user.id,
        goal=data.goal,
        max_steps=settings.agent_max_steps,
        max_tool_calls=settings.agent_max_tool_calls,
        allowed_tools=allowed_tools,
        correlation_id=data.correlation_id,
    )

    if blocking:
        # Run until paused (awaiting approval) or completed/failed
        await orchestrator.execute_run(session, run.id)
        run = await agent_repo.get_run(session, run.id)
    else:
        # Run in background task with its own DB session
        async def _run_bg(run_id: UUID):
            async with AsyncSessionLocal() as bg_session:
                await orchestrator.execute_run(bg_session, run_id)

        background_tasks.add_task(_run_bg, run.id)

    return await _build_run_response(session, run)


@router.get(
    "/runs",
    response_model=AgentRunListResponse,
)
async def list_agent_runs(
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.WORKSPACE_READ)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    mine_only: bool = Query(default=False),
    current_user: Annotated[User, Depends(get_current_user)] = None,  # type: ignore
) -> AgentRunListResponse:
    initiated_by = current_user.id if mine_only and current_user else None
    runs, total = await agent_repo.list_runs(
        session,
        workspace_id=membership.workspace_id,
        initiated_by=initiated_by,
        limit=limit,
        offset=offset,
    )

    items = []
    for r in runs:
        items.append(await _build_run_response(session, r))

    return AgentRunListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/runs/{run_id}",
    response_model=AgentRunResponse,
)
async def get_agent_run(
    run_id: UUID,
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.WORKSPACE_READ)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentRunResponse:
    run = await agent_repo.get_run(session, run_id, workspace_id=membership.workspace_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent run not found in this workspace",
        )
    return await _build_run_response(session, run)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=AgentRunResponse,
)
async def cancel_agent_run(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.WORKSPACE_READ)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentRunResponse:
    run = await agent_repo.get_run(session, run_id, workspace_id=membership.workspace_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent run not found",
        )

    # Cancel run & any pending approval
    await agent_repo.request_cancel(session, run.id)
    await agent_repo.cancel_pending_approvals(session, run.id)
    await agent_repo.transition_run_from_any(
        session,
        run.id,
        target=AgentRunStatus.CANCELLED,
        reason="Cancelled via user request",
    )
    await agent_repo.append_event(
        session,
        run_id=run.id,
        workspace_id=run.workspace_id,
        event_type="run_cancelled",
        data={"cancelled_by": str(current_user.id)},
    )

    updated_run = await agent_repo.get_run(session, run.id)
    return await _build_run_response(session, updated_run)


@router.get(
    "/runs/{run_id}/events",
)
async def get_run_events(
    run_id: UUID,
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.WORKSPACE_READ)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    after_seq: int = Query(default=0, ge=0),
    stream: bool = Query(default=False),
):
    run = await agent_repo.get_run(session, run_id, workspace_id=membership.workspace_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent run not found",
        )

    if not stream:
        events = await agent_repo.list_events(session, run.id, after_seq=after_seq)
        return [AgentEventResponse.model_validate(e) for e in events]

    # SSE Streaming mode
    async def event_generator() -> AsyncGenerator[str, None]:
        last_seq = after_seq
        while True:
            async with AsyncSessionLocal() as poll_session:
                fresh_run = await agent_repo.get_run(poll_session, run_id)
                events = await agent_repo.list_events(
                    poll_session, run_id, after_seq=last_seq, limit=100
                )
                for ev in events:
                    last_seq = ev.seq
                    ev_data = AgentEventResponse.model_validate(ev).model_dump(mode="json")
                    yield f"event: {ev.event_type}\ndata: {json.dumps(ev_data)}\n\n"

                # Stop streaming if run is terminal or awaiting approval
                if fresh_run and fresh_run.status in [
                    AgentRunStatus.COMPLETED.value,
                    AgentRunStatus.FAILED.value,
                    AgentRunStatus.CANCELLED.value,
                    AgentRunStatus.AWAITING_APPROVAL.value,
                ] and not events:
                    yield "event: done\ndata: {}\n\n"
                    break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=AgentRunResponse,
)
async def approve_agent_action(
    approval_id: UUID,
    data: ApprovalDecisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.WORKSPACE_READ)),
    ],
    orchestrator: Annotated[AgentOrchestrator, Depends(get_agent_orchestrator)],
    session: Annotated[AsyncSession, Depends(get_session)],
    blocking: bool = Query(default=True),
) -> AgentRunResponse:
    try:
        approval, _step = await orchestrator.approval_service.approve_request(
            session,
            approval_id=approval_id,
            approver=current_user,
            workspace_id=membership.workspace_id,
            reason=data.reason,
        )
    except ApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST
            if exc.code != "permission_denied"
            else status.HTTP_403_FORBIDDEN,
            detail=f"{exc.code}: {exc.message}",
        ) from exc

    if blocking:
        await orchestrator.resume_after_approval(session, approval.run_id)

    run = await agent_repo.get_run(session, approval.run_id)
    return await _build_run_response(session, run)


@router.post(
    "/approvals/{approval_id}/reject",
    response_model=AgentRunResponse,
)
async def reject_agent_action(
    approval_id: UUID,
    data: ApprovalDecisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.WORKSPACE_READ)),
    ],
    orchestrator: Annotated[AgentOrchestrator, Depends(get_agent_orchestrator)],
    session: Annotated[AsyncSession, Depends(get_session)],
    blocking: bool = Query(default=True),
) -> AgentRunResponse:
    try:
        approval = await orchestrator.approval_service.reject_request(
            session,
            approval_id=approval_id,
            approver=current_user,
            workspace_id=membership.workspace_id,
            reason=data.reason,
        )
    except ApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{exc.code}: {exc.message}",
        ) from exc

    if blocking:
        await orchestrator.resume_after_approval(session, approval.run_id)

    run = await agent_repo.get_run(session, approval.run_id)
    return await _build_run_response(session, run)
