"""Persistence for agent runs, steps, approvals and execution events.

All state changes that guard a security invariant (run transitions, approval
decisions) are atomic compare-and-set UPDATEs so concurrent requests cannot both
succeed. Reads that feed authorization decisions use ``populate_existing`` so a
stale identity-map object is never trusted.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_state import (
    TERMINAL_RUN_STATUSES,
    AgentRunStatus,
    ApprovalStatus,
    InvalidRunTransitionError,
    StepStatus,
    ensure_transition,
)
from app.models.agent import (
    AgentApprovalRequest,
    AgentExecutionEvent,
    AgentRun,
    AgentStep,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------ runs


async def create_run(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    initiated_by: UUID,
    goal: str,
    max_steps: int,
    max_tool_calls: int,
    allowed_tools: list[str],
    correlation_id: str | None,
) -> AgentRun:
    run = AgentRun(
        workspace_id=workspace_id,
        initiated_by=initiated_by,
        goal=goal,
        status=AgentRunStatus.CREATED.value,
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
        allowed_tools=allowed_tools,
        correlation_id=correlation_id,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    workspace_id: UUID | None = None,
) -> AgentRun | None:
    query = (
        select(AgentRun)
        .where(AgentRun.id == run_id)
        .execution_options(populate_existing=True)
    )
    if workspace_id is not None:
        query = query.where(AgentRun.workspace_id == workspace_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def list_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    initiated_by: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[AgentRun], int]:
    base = select(AgentRun).where(AgentRun.workspace_id == workspace_id)
    count_query = select(func.count(AgentRun.id)).where(
        AgentRun.workspace_id == workspace_id
    )
    if initiated_by is not None:
        base = base.where(AgentRun.initiated_by == initiated_by)
        count_query = count_query.where(AgentRun.initiated_by == initiated_by)

    result = await session.execute(
        base.order_by(AgentRun.created_at.desc())
        .limit(limit)
        .offset(offset)
        .execution_options(populate_existing=True)
    )
    total = (await session.execute(count_query)).scalar_one()
    return list(result.scalars().all()), total


async def count_active_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    initiated_by: UUID,
) -> int:
    result = await session.execute(
        select(func.count(AgentRun.id)).where(
            AgentRun.workspace_id == workspace_id,
            AgentRun.initiated_by == initiated_by,
            AgentRun.status.in_(
                [
                    AgentRunStatus.CREATED.value,
                    AgentRunStatus.RUNNING.value,
                ]
            ),
        )
    )
    return result.scalar_one()


async def transition_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    expected: AgentRunStatus,
    target: AgentRunStatus,
    reason: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    deadline_at: datetime | None = None,
    final_answer: str | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> bool:
    """Atomically move a run ``expected -> target``.

    Raises ``InvalidRunTransitionError`` if the edge is illegal in the state
    machine. Returns ``False`` when the run is no longer in ``expected`` (a
    concurrent writer won), so callers must treat that as "do not proceed".
    """
    ensure_transition(expected, target)

    values: dict[str, Any] = {
        "status": target.value,
        "updated_at": utcnow(),
    }
    if reason is not None:
        values["status_reason"] = reason
    if error_code is not None:
        values["error_code"] = error_code
    if error_message is not None:
        values["error_message"] = error_message[:500]
    if deadline_at is not None:
        values["deadline_at"] = deadline_at
    if final_answer is not None:
        values["final_answer"] = final_answer
    if sources is not None:
        values["sources"] = sources
    if target == AgentRunStatus.RUNNING and expected == AgentRunStatus.CREATED:
        values["started_at"] = utcnow()
    if target in TERMINAL_RUN_STATUSES:
        values["finished_at"] = utcnow()

    result = await session.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.status == expected.value)
        .values(**values)
    )
    await session.commit()
    return result.rowcount == 1


async def transition_run_from_any(
    session: AsyncSession,
    run_id: UUID,
    *,
    target: AgentRunStatus,
    reason: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> AgentRunStatus | None:
    """Move a non-terminal run to ``target`` using its freshly read status.

    Returns the previous status if the transition was applied, otherwise ``None``
    (run missing, already terminal or lost a race).
    """
    run = await get_run(session, run_id)
    if run is None:
        return None
    current = AgentRunStatus(run.status)
    try:
        ensure_transition(current, target)
    except InvalidRunTransitionError:
        return None
    applied = await transition_run(
        session,
        run_id,
        expected=current,
        target=target,
        reason=reason,
        error_code=error_code,
        error_message=error_message,
    )
    return current if applied else None


async def request_cancel(session: AsyncSession, run_id: UUID) -> None:
    await session.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id)
        .values(cancel_requested=True, updated_at=utcnow())
    )
    await session.commit()


async def bump_run_counters(
    session: AsyncSession,
    run_id: UUID,
    *,
    steps: int = 0,
    tool_calls: int = 0,
    denials: int = 0,
) -> None:
    await session.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id)
        .values(
            current_step=AgentRun.current_step + steps,
            tool_call_count=AgentRun.tool_call_count + tool_calls,
            denial_count=AgentRun.denial_count + denials,
            updated_at=utcnow(),
        )
    )
    await session.commit()


async def update_run_sources(
    session: AsyncSession,
    run_id: UUID,
    sources: list[dict[str, Any]],
) -> None:
    await session.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id)
        .values(sources=sources, updated_at=utcnow())
    )
    await session.commit()


# ----------------------------------------------------------------- steps


async def create_step(
    session: AsyncSession,
    *,
    run: AgentRun,
    step_index: int,
    tool_name: str,
    side_effect: str | None,
    reason: str | None,
    arguments: dict[str, Any] | None,
    status: StepStatus = StepStatus.PENDING,
) -> AgentStep:
    step = AgentStep(
        run_id=run.id,
        workspace_id=run.workspace_id,
        step_index=step_index,
        tool_name=tool_name,
        side_effect=side_effect,
        reason=reason[:500] if reason else None,
        arguments=arguments,
        status=status.value,
        idempotency_key=f"{run.id}:{step_index}",
        started_at=utcnow(),
    )
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return step


async def get_step(session: AsyncSession, step_id: UUID) -> AgentStep | None:
    result = await session.execute(
        select(AgentStep)
        .where(AgentStep.id == step_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def list_steps(session: AsyncSession, run_id: UUID) -> list[AgentStep]:
    result = await session.execute(
        select(AgentStep)
        .where(AgentStep.run_id == run_id)
        .order_by(AgentStep.step_index.asc())
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def finish_step(
    session: AsyncSession,
    step_id: UUID,
    *,
    status: StepStatus,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    await session.execute(
        update(AgentStep)
        .where(AgentStep.id == step_id)
        .values(
            status=status.value,
            result=result,
            error_code=error_code,
            error_message=error_message[:500] if error_message else None,
            finished_at=utcnow(),
        )
    )
    await session.commit()


# ------------------------------------------------------------- approvals


async def create_approval(
    session: AsyncSession,
    *,
    run: AgentRun,
    step: AgentStep,
    tool_name: str,
    payload: dict[str, Any],
    payload_hash: str,
    expires_at: datetime,
) -> AgentApprovalRequest:
    approval = AgentApprovalRequest(
        run_id=run.id,
        step_id=step.id,
        workspace_id=run.workspace_id,
        requested_by=run.initiated_by,
        tool_name=tool_name,
        payload=payload,
        payload_hash=payload_hash,
        expires_at=expires_at,
    )
    session.add(approval)
    await session.commit()
    await session.refresh(approval)
    return approval


async def get_approval(
    session: AsyncSession, approval_id: UUID
) -> AgentApprovalRequest | None:
    result = await session.execute(
        select(AgentApprovalRequest)
        .where(AgentApprovalRequest.id == approval_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def get_pending_approval_for_run(
    session: AsyncSession, run_id: UUID
) -> AgentApprovalRequest | None:
    result = await session.execute(
        select(AgentApprovalRequest)
        .where(
            AgentApprovalRequest.run_id == run_id,
            AgentApprovalRequest.status == ApprovalStatus.PENDING.value,
        )
        .execution_options(populate_existing=True)
    )
    return result.scalars().first()


async def list_approvals_for_run(
    session: AsyncSession, run_id: UUID
) -> list[AgentApprovalRequest]:
    result = await session.execute(
        select(AgentApprovalRequest)
        .where(AgentApprovalRequest.run_id == run_id)
        .order_by(AgentApprovalRequest.created_at.asc())
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def claim_approval_decision(
    session: AsyncSession,
    approval_id: UUID,
    *,
    decision: ApprovalStatus,
    decided_by: UUID,
    reason: str | None = None,
) -> bool:
    """Atomically decide a PENDING, unexpired approval exactly once."""
    now = utcnow()
    result = await session.execute(
        update(AgentApprovalRequest)
        .where(
            AgentApprovalRequest.id == approval_id,
            AgentApprovalRequest.status == ApprovalStatus.PENDING.value,
            AgentApprovalRequest.expires_at > now,
        )
        .values(
            status=decision.value,
            decided_by=decided_by,
            decided_at=now,
            decision_reason=reason[:500] if reason else None,
        )
    )
    await session.commit()
    return result.rowcount == 1


async def advance_approval(
    session: AsyncSession,
    approval_id: UUID,
    *,
    expected: ApprovalStatus,
    target: ApprovalStatus,
    reason: str | None = None,
) -> bool:
    values: dict[str, Any] = {"status": target.value}
    if reason is not None:
        values["decision_reason"] = reason[:500]
    if target == ApprovalStatus.EXECUTED:
        values["executed_at"] = utcnow()
    result = await session.execute(
        update(AgentApprovalRequest)
        .where(
            AgentApprovalRequest.id == approval_id,
            AgentApprovalRequest.status == expected.value,
        )
        .values(**values)
    )
    await session.commit()
    return result.rowcount == 1


async def cancel_pending_approvals(session: AsyncSession, run_id: UUID) -> int:
    result = await session.execute(
        update(AgentApprovalRequest)
        .where(
            AgentApprovalRequest.run_id == run_id,
            AgentApprovalRequest.status == ApprovalStatus.PENDING.value,
        )
        .values(status=ApprovalStatus.CANCELLED.value)
    )
    await session.commit()
    return result.rowcount


# ---------------------------------------------------------------- events


async def append_event(
    session: AsyncSession,
    *,
    run_id: UUID,
    workspace_id: UUID,
    event_type: str,
    step_id: UUID | None = None,
    data: dict[str, Any] | None = None,
) -> AgentExecutionEvent:
    """Append a sequenced event. The sequence is allocated atomically on the run row."""
    result = await session.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id)
        .values(event_seq=AgentRun.event_seq + 1)
        .returning(AgentRun.event_seq)
    )
    seq = result.scalar_one()
    event = AgentExecutionEvent(
        run_id=run_id,
        workspace_id=workspace_id,
        seq=seq,
        event_type=event_type,
        step_id=step_id,
        data=data,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def list_events(
    session: AsyncSession,
    run_id: UUID,
    *,
    after_seq: int = 0,
    limit: int = 500,
) -> list[AgentExecutionEvent]:
    result = await session.execute(
        select(AgentExecutionEvent)
        .where(
            AgentExecutionEvent.run_id == run_id,
            AgentExecutionEvent.seq > after_seq,
        )
        .order_by(AgentExecutionEvent.seq.asc())
        .limit(limit)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())
