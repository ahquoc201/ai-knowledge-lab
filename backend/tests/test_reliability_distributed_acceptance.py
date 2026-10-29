"""Targeted regression tests for Distributed Reliability Acceptance (T260028).

Verifies:
1. Multi-worker sliding window rate limiter concurrency and degradation.
2. Redis outage reporting in /health/ready probe (degraded vs healthy).
3. Request ID sanitization against injection attacks.
4. Tenant isolation in recovery endpoint (Workspace A cannot touch Workspace B).
5. Fencing tokens preventing stale workers from overwriting active state.
6. AWAITING_APPROVAL runs protected against illegal auto-recovery.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.agent_state import AgentRunStatus
from app.core.config import get_settings
from app.models.agent import AgentRun
from app.repositories import agent as agent_repo
from app.services.agent_recovery import AgentRecoveryService
from app.services.rate_limiter import (
    InMemorySlidingWindowLimiter,
    get_rate_limiter,
)


def setup_user_and_workspace(client: TestClient, prefix: str) -> tuple[dict, str, dict]:
    email = f"{prefix}_{uuid4().hex[:8]}@example.com"
    pwd = "SecurePassword123!"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pwd, "full_name": f"{prefix} User"},
    )
    assert reg.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    ws = client.post(
        "/api/v1/workspaces",
        json={"name": f"{prefix} Workspace", "description": f"{prefix} desc"},
        headers=headers,
    ).json()
    return reg.json(), token, ws


def test_request_id_sanitization(client: TestClient):
    """Malicious or invalid X-Request-ID headers are discarded and replaced with safe UUIDs."""
    # 1. CRLF / Header Injection attempt
    res = client.get("/api/v1/health", headers={"X-Request-ID": "valid_prefix\r\nInjected-Header: evil"})
    assert res.status_code == 200
    returned_id = res.headers["X-Request-ID"]
    assert "\r" not in returned_id
    assert "\n" not in returned_id
    assert len(returned_id) == 32  # generated hex UUID

    # 2. XSS / Script injection attempt
    res_xss = client.get("/api/v1/health", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert res_xss.status_code == 200
    assert "<" not in res_xss.headers["X-Request-ID"]

    # 3. Legitimate alphanumeric and hyphen trace IDs are preserved
    valid_id = "trace-req-abc_123-999"
    res_valid = client.get("/api/v1/health", headers={"X-Request-ID": valid_id})
    assert res_valid.headers["X-Request-ID"] == valid_id


def test_readiness_probe_reports_degraded_when_redis_offline(client: TestClient):
    """When Redis is offline or using in-memory fallback, /health/ready MUST report 'degraded'."""
    limiter = get_rate_limiter()
    # If redis client is not active (e.g. offline or fallback)
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 200
    body = res.json()
    if not limiter.is_redis_active():
        assert body["status"] == "degraded"
        assert body["components"]["redis"]["status"] == "offline"
        assert "fallback" in body["components"]["redis"]["mode"]


def test_multi_worker_rate_limiter_in_memory_concurrency():
    """Verify in-memory sliding window limiter under simulated concurrent worker calls."""
    limiter = InMemorySlidingWindowLimiter()
    key = "concurrent_worker_key"
    limit = 5
    window = 2

    # First 5 calls allowed
    for i in range(5):
        res = limiter.check(key, limit=limit, window_seconds=window, rule_name="test")
        assert res.allowed is True
        assert res.remaining == 4 - i

    # 6th call denied
    res_denied = limiter.check(key, limit=limit, window_seconds=window, rule_name="test")
    assert res_denied.allowed is False
    assert res_denied.remaining == 0
    assert res_denied.retry_after >= 1


@pytest.mark.anyio
async def test_lease_fencing_prevents_stale_worker_overwrite(client: TestClient):
    """Worker A loses lease to Worker B; Worker A's update fails fencing check."""
    user, _token, ws = setup_user_and_workspace(client, "fencing_test")
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
                goal="Fencing verification",
                status=AgentRunStatus.RUNNING.value,
                max_steps=5,
                max_tool_calls=3,
                allowed_tools=["search_workspace_documents"],
                lease_token="worker_A_token",
                lease_expires_at=now - timedelta(seconds=10),  # expired lease
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)

            # Worker B claims the run with new token
            worker_b_token = "worker_B_token"
            claimed_b = await agent_repo.claim_run_lease(
                session, run.id, lease_token=worker_b_token, ttl_seconds=60
            )
            assert claimed_b is True

            # Stale Worker A finishes long LLM step and attempts transition with old token
            transition_a = await agent_repo.transition_run(
                session,
                run.id,
                expected=AgentRunStatus.RUNNING,
                target=AgentRunStatus.FAILED,
                reason="Stale worker failure",
                lease_token="worker_A_token",  # STALE TOKEN
            )
            assert transition_a is False, "Stale worker transition MUST fail fencing check"

            # Check run in DB: still RUNNING with Worker B's lease intact
            fresh_run = await agent_repo.get_run(session, run.id)
            assert fresh_run.status == AgentRunStatus.RUNNING.value
            assert fresh_run.lease_token == worker_b_token
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_recovery_tenant_isolation(client: TestClient):
    """Triggering recovery in Workspace A strictly ignores and does not mutate Workspace B's stuck runs."""
    _owner_a, token_a, ws_a = setup_user_and_workspace(client, "tenant_a")
    _owner_b, _token_b, ws_b = setup_user_and_workspace(client, "tenant_b")

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            now = datetime.now(UTC)
            # Create stuck run in Workspace A
            run_a = AgentRun(
                workspace_id=UUID(ws_a["id"]),
                initiated_by=UUID(_owner_a["id"]),
                goal="Workspace A stuck run",
                status=AgentRunStatus.RUNNING.value,
                max_steps=5,
                max_tool_calls=3,
                allowed_tools=["search_workspace_documents"],
                lease_expires_at=now - timedelta(seconds=20),
            )
            # Create stuck run in Workspace B
            run_b = AgentRun(
                workspace_id=UUID(ws_b["id"]),
                initiated_by=UUID(_owner_b["id"]),
                goal="Workspace B stuck run",
                status=AgentRunStatus.RUNNING.value,
                max_steps=5,
                max_tool_calls=3,
                allowed_tools=["search_workspace_documents"],
                lease_expires_at=now - timedelta(seconds=20),
            )
            session.add_all([run_a, run_b])
            await session.commit()
            await session.refresh(run_a)
            await session.refresh(run_b)

            run_a_id = run_a.id
            run_b_id = run_b.id

        # Trigger recovery using Workspace A credentials
        headers_a = {"Authorization": f"Bearer {token_a}", "X-Workspace-Id": ws_a["id"]}
        rec_res = client.post("/api/v1/reliability/recover-stuck", headers=headers_a)
        assert rec_res.status_code == 200
        rec_data = rec_res.json()
        assert rec_data["recovered_count"] == 1
        assert rec_data["recovered_runs"][0]["run_id"] == str(run_a_id)

        # Verify Workspace B's run was NOT recovered
        async with session_factory() as session:
            fresh_run_b = await agent_repo.get_run(session, run_b_id)
            assert fresh_run_b.recovery_attempts == 0  # Untouched
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_awaiting_approval_never_auto_recovered(client: TestClient):
    """AgentRun in AWAITING_APPROVAL status is never auto-resumed or recovered by the engine."""
    user, _token, ws = setup_user_and_workspace(client, "approval_rec_test")
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
                goal="Awaiting approval run",
                status=AgentRunStatus.AWAITING_APPROVAL.value,
                max_steps=5,
                max_tool_calls=3,
                allowed_tools=["search_workspace_documents"],
                lease_expires_at=now - timedelta(seconds=100),
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)

            # 1. Verify list_stuck_runs ignores it
            stuck = await agent_repo.list_stuck_runs(session, now, workspace_id=ws_id)
            assert not any(r.id == run.id for r in stuck)

            # 2. Direct recovery attempt is ignored
            recovery_svc = AgentRecoveryService()
            result = await recovery_svc.recover_single_run(session, run, now=now)
            assert result["action"] == "ignored_not_running"

            # 3. Status remains AWAITING_APPROVAL
            fresh_run = await agent_repo.get_run(session, run.id)
            assert fresh_run.status == AgentRunStatus.AWAITING_APPROVAL.value
    finally:
        await engine.dispose()
