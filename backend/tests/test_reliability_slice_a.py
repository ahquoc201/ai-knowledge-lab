"""Targeted regression tests for Slice A: Resource Governance & Rate Limiting (T260028)."""

import asyncio
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.services.inference_governor import (
    InferenceCapacityExceededError,
    InferenceGovernor,
    InferenceQueueTimeoutError,
)
from app.services.rate_limiter import (
    InMemorySlidingWindowLimiter,
    RateLimiter,
    get_rate_limiter,
)


def setup_auth_user(client: TestClient, email: str | None = None) -> dict[str, str]:
    target_email = email or f"user_{uuid4().hex[:8]}@example.com"
    pwd = "SecureTestPassword123!"
    client.post(
        "/api/v1/auth/register",
        json={"email": target_email, "password": pwd, "full_name": "Test User"},
    )
    res = client.post(
        "/api/v1/auth/login",
        json={"email": target_email, "password": pwd},
    )
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_in_memory_sliding_window_limiter():
    limiter = InMemorySlidingWindowLimiter()
    key = "test_key_1"
    limit = 3
    window = 2

    # First 3 requests must pass
    for i in range(3):
        res = limiter.check(key, limit, window, "test_rule")
        assert res.allowed is True
        assert res.remaining == 3 - (i + 1)

    # 4th request must be rejected
    res4 = limiter.check(key, limit, window, "test_rule")
    assert res4.allowed is False
    assert res4.remaining == 0
    assert res4.retry_after > 0

    # Sleep window duration to test reset
    time.sleep(2.1)
    res_reset = limiter.check(key, limit, window, "test_rule")
    assert res_reset.allowed is True
    assert res_reset.remaining == 2


def test_rate_limiter_auth_login_endpoint(client: TestClient, monkeypatch):
    """Verify auth endpoints enforce rate limits and return HTTP 429 with Retry-After headers."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "rate_limit_auth_per_minute", 3)

    ip = f"198.51.100.{uuid4().int % 200 + 10}"
    headers = {"X-Forwarded-For": ip}

    # Trigger 3 login attempts with wrong password
    for _ in range(3):
        res = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "WrongPassword!"},
            headers=headers,
        )
        assert res.status_code == 401

    # 4th attempt must be rejected with 429
    res_limited = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "WrongPassword!"},
        headers=headers,
    )
    assert res_limited.status_code == 429
    assert "Rate limit exceeded" in res_limited.json()["detail"]
    assert "Retry-After" in res_limited.headers
    assert res_limited.headers.get("X-RateLimit-Remaining") == "0"


def test_rate_limiter_cross_tenant_isolation(client: TestClient, monkeypatch):
    """User cannot bypass user rate limits by simply switching workspace header."""
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "rate_limit_agent_runs_per_user_per_minute", 3)

    user_headers = setup_auth_user(client)

    # Create workspace A and workspace B
    ws_a = client.post(
        "/api/v1/workspaces",
        json={"name": "Workspace A", "description": "Rate limit test"},
        headers=user_headers,
    ).json()["id"]

    ws_b = client.post(
        "/api/v1/workspaces",
        json={"name": "Workspace B", "description": "Rate limit test"},
        headers=user_headers,
    ).json()["id"]

    limiter = get_rate_limiter()
    # Configure user rate limit key
    user_id = client.get("/api/v1/auth/me", headers=user_headers).json()["id"]

    # Fill user budget for agent runs (limit = 3)
    for _ in range(3):
        limiter.check(user_id, limit=3, window_seconds=60, rule_name="agent_run_user")

    # Creating agent run on workspace A must fail with 429
    res_a = client.post(
        "/api/v1/agent/runs",
        json={"goal": "Search documents", "allowed_tools": ["search_workspace_documents"]},
        headers={**user_headers, "X-Workspace-Id": ws_a},
    )
    assert res_a.status_code == 429
    assert "agent_run_user" in res_a.json()["detail"]

    # Switching to workspace B MUST STILL FAIL because user limit is exceeded!
    res_b = client.post(
        "/api/v1/agent/runs",
        json={"goal": "Search documents", "allowed_tools": ["search_workspace_documents"]},
        headers={**user_headers, "X-Workspace-Id": ws_b},
    )
    assert res_b.status_code == 429
    assert "agent_run_user" in res_b.json()["detail"]


@pytest.mark.anyio
async def test_inference_governor_concurrency_and_admission_control():
    """Verify governor admission control: rejects when queue exceeds max_queue_size."""
    governor = InferenceGovernor(max_concurrency=1, max_queue_size=2, queue_timeout_seconds=2.0)

    acquired_leases = []
    task_done = asyncio.Event()

    async def worker(worker_id: int):
        async with governor.acquire(caller_info=f"worker_{worker_id}") as lease:
            acquired_leases.append(lease.lease_id)
            await task_done.wait()

    # Launch worker 1: acquires the 1 available slot
    t1 = asyncio.create_task(worker(1))
    await asyncio.sleep(0.05)
    assert governor.metrics.active_inferences == 1
    assert governor.metrics.queued_requests == 0

    # Launch worker 2 & 3: fill the queue of size 2
    t2 = asyncio.create_task(worker(2))
    t3 = asyncio.create_task(worker(3))
    await asyncio.sleep(0.05)
    assert governor.metrics.queued_requests == 2

    # Launch worker 4: queue is full (2/2) -> MUST RAISE 503 InferenceCapacityExceededError immediately
    with pytest.raises(InferenceCapacityExceededError) as exc_info:
        async with governor.acquire(caller_info="worker_4"):
            pass
    assert exc_info.value.status_code == 503
    assert governor.metrics.total_rejected == 1

    # Release worker 1
    task_done.set()
    await asyncio.gather(t1, t2, t3)
    assert len(acquired_leases) == 3


@pytest.mark.anyio
async def test_inference_governor_queue_timeout():
    """Verify queued request times out if slot does not become available within timeout."""
    governor = InferenceGovernor(max_concurrency=1, max_queue_size=5, queue_timeout_seconds=0.2)
    slot_occupied = asyncio.Event()

    async def long_occupant():
        async with governor.acquire(caller_info="occupant"):
            await slot_occupied.wait()

    t_occ = asyncio.create_task(long_occupant())
    await asyncio.sleep(0.05)

    # Attempt to acquire with small timeout
    start_time = time.time()
    with pytest.raises(InferenceQueueTimeoutError) as exc_info:
        async with governor.acquire(caller_info="timeout_candidate", timeout=0.2):
            pass
    duration = time.time() - start_time
    assert duration >= 0.18
    assert exc_info.value.status_code == 504
    assert governor.metrics.total_timeouts == 1

    # Cleanup occupant
    slot_occupied.set()
    await t_occ


def test_rate_limiter_redis_graceful_fallback():
    """When Redis is unavailable or URL is invalid, limiter falls back gracefully to in-memory."""
    # Point to invalid redis port
    limiter = RateLimiter(redis_url="redis://127.0.0.1:54321/0")
    assert limiter.is_redis_active() is False

    # Check must still function seamlessly using in-memory fallback
    res = limiter.check("fallback_user_1", limit=2, window_seconds=10, rule_name="fallback_test")
    assert res.allowed is True
    assert res.remaining == 1

    res2 = limiter.check("fallback_user_1", limit=2, window_seconds=10, rule_name="fallback_test")
    assert res2.allowed is True
    assert res2.remaining == 0

    res3 = limiter.check("fallback_user_1", limit=2, window_seconds=10, rule_name="fallback_test")
    assert res3.allowed is False
