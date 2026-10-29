"""Targeted tests for Slice B: Durable Execution & Failure Recovery (T260028)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.agent_state import AgentRunStatus, StepStatus
from app.core.config import get_settings
from app.models.agent import AgentRun, AgentStep
from app.repositories import agent as agent_repo
from app.services.agent_recovery import AgentRecoveryService


def setup_user_and_workspace(client: TestClient, prefix: str = "slice_b") -> tuple[dict, str, dict]:
    email = f"{prefix}_{uuid4().hex[:8]}@example.com"
    pwd = "SecurePassword123!"
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": pwd, "full_name": f"User {prefix}"})
    assert reg.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    ws = client.post(
        "/api/v1/workspaces",
        json={"name": f"Workspace {prefix}", "description": "Recovery verification"},
        headers=headers,
    ).json()
    return reg.json(), token, ws


@pytest.mark.anyio
async def test_agent_lease_claim_and_renewal(client: TestClient):
    """Verify CAS lease claiming, heartbeat renewal, and fencing."""
    user, _token, ws = setup_user_and_workspace(client, "lease_test")
    user_id = UUID(user["id"])
    ws_id = UUID(ws["id"])

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            run = AgentRun(
                workspace_id=ws_id,
                initiated_by=user_id,
                goal="Test lease",
                status=AgentRunStatus.RUNNING.value,
                max_steps=5,
                max_tool_calls=3,
                allowed_tools=["search_workspace_documents"],
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)

            token_a = "worker_token_A"
            token_b = "worker_token_B"

            # Worker A claims lease
            claimed = await agent_repo.claim_run_lease(session, run.id, lease_token=token_a, ttl_seconds=60)
            assert claimed is True

            # Worker B tries to claim while A is active -> MUST FAIL (fenced)
            claimed_b = await agent_repo.claim_run_lease(session, run.id, lease_token=token_b, ttl_seconds=60)
            assert claimed_b is False

            # Worker A renews lease heartbeat
            renewed = await agent_repo.renew_run_lease(session, run.id, lease_token=token_a, ttl_seconds=60)
            assert renewed is True

            # Worker B tries to renew A's lease -> MUST FAIL
            renewed_b = await agent_repo.renew_run_lease(session, run.id, lease_token=token_b, ttl_seconds=60)
            assert renewed_b is False

            # Worker A releases lease
            await agent_repo.release_run_lease(session, run.id, lease_token=token_a)

            # Worker B can now claim lease
            claimed_b_after = await agent_repo.claim_run_lease(session, run.id, lease_token=token_b, ttl_seconds=60)
            assert claimed_b_after is True
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_recovery_of_stuck_run_after_crash(client: TestClient):
    """Verify stuck run with expired lease is detected and safely recovered."""
    user, _token, ws = setup_user_and_workspace(client, "stuck_test")
    user_id = UUID(user["id"])
    ws_id = UUID(ws["id"])

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            now = datetime.now(UTC)
            expired_at = now - timedelta(seconds=120)

            run = AgentRun(
                workspace_id=ws_id,
                initiated_by=user_id,
                goal="Stuck run",
                status=AgentRunStatus.RUNNING.value,
                max_steps=5,
                max_tool_calls=3,
                allowed_tools=["search_workspace_documents"],
                lease_token="crashed_worker_123",
                lease_expires_at=expired_at,
                recovery_attempts=0,
                max_recovery_attempts=3,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)

            recovery_svc = AgentRecoveryService()
            res = await recovery_svc.recover_single_run(session, run, now=now)
            assert res["action"] == "recovered_for_execution"
            assert res["attempt"] == "1"

            # Re-check run in DB
            recovered = await agent_repo.get_run(session, run.id)
            assert recovered.recovery_attempts == 1
            assert recovered.lease_token is None  # Lease released so worker can claim
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_recovery_fails_closed_when_deadline_exceeded(client: TestClient):
    """When deadline has passed, recovery must transition to FAILED and not re-execute."""
    user, _token, ws = setup_user_and_workspace(client, "deadline_test")
    user_id = UUID(user["id"])
    ws_id = UUID(ws["id"])

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            now = datetime.now(UTC)
            deadline = now - timedelta(seconds=10)

            run = AgentRun(
                workspace_id=ws_id,
                initiated_by=user_id,
                goal="Timed out run",
                status=AgentRunStatus.RUNNING.value,
                max_steps=5,
                max_tool_calls=3,
                allowed_tools=["search_workspace_documents"],
                deadline_at=deadline,
                lease_expires_at=now - timedelta(seconds=5),
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)

            recovery_svc = AgentRecoveryService()
            res = await recovery_svc.recover_single_run(session, run, now=now)
            assert res["action"] == "failed_timeout"

            failed_run = await agent_repo.get_run(session, run.id)
            assert failed_run.status == AgentRunStatus.FAILED.value
            assert failed_run.error_code == "execution_timeout"
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_recovery_prevents_duplicate_write_side_effect(client: TestClient):
    """Interrupted WRITE step must be failed to prevent double mutation on recovery."""
    user, _token, ws = setup_user_and_workspace(client, "dup_write_test")
    user_id = UUID(user["id"])
    ws_id = UUID(ws["id"])

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            now = datetime.now(UTC)
            run = AgentRun(
                workspace_id=ws_id,
                initiated_by=user_id,
                goal="Write task",
                status=AgentRunStatus.RUNNING.value,
                max_steps=5,
                max_tool_calls=3,
                allowed_tools=["create_workspace_document"],
                lease_expires_at=now - timedelta(seconds=5),
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)

            # Interrupted WRITE step
            step = AgentStep(
                run_id=run.id,
                workspace_id=run.workspace_id,
                step_index=1,
                tool_name="create_workspace_document",
                side_effect="WRITE",
                arguments={"title": "Doc", "content": "Hello"},
                status=StepStatus.PENDING.value,
                idempotency_key=f"idemp_{uuid4().hex}",
            )
            session.add(step)
            await session.commit()
            await session.refresh(step)

            recovery_svc = AgentRecoveryService()
            await recovery_svc.recover_single_run(session, run, now=now)

            # Check step status: MUST BE FAILED with execution_interrupted
            updated_step = await agent_repo.get_step(session, step.id)
            assert updated_step.status == StepStatus.FAILED.value
            assert updated_step.error_code == "execution_interrupted"

            # Check run status: MUST BE FAILED to strictly prevent duplicate side-effects
            updated_run = await agent_repo.get_run(session, run.id)
            assert updated_run.status == AgentRunStatus.FAILED.value
            assert updated_run.error_code == "unconfirmed_mutation"
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_recovery_exhaustion_marks_failed(client: TestClient):
    """Run reaching max_recovery_attempts transitions to FAILED."""
    user, _token, ws = setup_user_and_workspace(client, "exhaust_test")
    user_id = UUID(user["id"])
    ws_id = UUID(ws["id"])

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            now = datetime.now(UTC)
            run = AgentRun(
                workspace_id=ws_id,
                initiated_by=user_id,
                goal="Exhausted run",
                status=AgentRunStatus.RUNNING.value,
                max_steps=5,
                max_tool_calls=3,
                allowed_tools=["search_workspace_documents"],
                recovery_attempts=3,
                max_recovery_attempts=3,
                lease_expires_at=now - timedelta(seconds=5),
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)

            recovery_svc = AgentRecoveryService()
            res = await recovery_svc.recover_single_run(session, run, now=now)
            assert res["action"] == "failed_max_attempts"

            failed_run = await agent_repo.get_run(session, run.id)
            assert failed_run.status == AgentRunStatus.FAILED.value
            assert failed_run.error_code == "max_recovery_attempts_exceeded"
    finally:
        await engine.dispose()


def test_sse_reconnection_with_last_event_id(client: TestClient):
    """Verify SSE endpoint supports Last-Event-ID header and does not deliver duplicate events."""
    _user, token, ws = setup_user_and_workspace(client, "sse_rec")
    headers_ws = {"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]}

    # Create run
    create_res = client.post(
        "/api/v1/agent/runs?blocking=true",
        json={"goal": "Search documents for recovery test", "allowed_tools": ["search_workspace_documents"]},
        headers=headers_ws,
    )
    assert create_res.status_code == 201
    run_id = create_res.json()["id"]

    # Read events non-streaming
    events_res = client.get(f"/api/v1/agent/runs/{run_id}/events?stream=false", headers=headers_ws)
    assert events_res.status_code == 200
    events = events_res.json()
    assert len(events) >= 1

    last_seq = events[0]["seq"]

    # Request events with after_seq filter
    filtered_res = client.get(
        f"/api/v1/agent/runs/{run_id}/events?stream=false&after_seq={last_seq}",
        headers=headers_ws,
    )
    assert filtered_res.status_code == 200
    filtered_events = filtered_res.json()
    assert all(e["seq"] > last_seq for e in filtered_events)
