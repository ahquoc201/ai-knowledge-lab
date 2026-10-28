"""Dedicated Security Verification Suite for Agent Approvals (T260025).

Explicitly verifies:
1. Concurrent approval race condition: Atomic conditional update ensures only ONE approver can claim a pending approval.
2. Approval payload tampering detection via cryptographic hash validation.
3. Exact approved payload execution (no parameter hijacking).
4. Expired approval rejection.
5. Cross-workspace approval attempt isolation.
6. Replay resistance under retry.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.agent_state import ApprovalStatus
from app.core.config import get_settings
from app.llm.base import LLMMessage, LLMProvider
from app.llm.ollama import get_ollama_llm_provider
from app.main import app
from app.repositories import agent as agent_repo


@pytest.fixture(autouse=True)
def mock_embedding_query(monkeypatch):
    monkeypatch.setattr(
        "app.services.semantic_search._embed_query",
        lambda text: [0.05] * 384,
    )


class ScriptedLLM(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.call_count = 0

    async def generate(self, messages: list[LLMMessage]) -> str:
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return json.dumps({
            "action": "final_answer",
            "answer": "Completed task.",
            "citations": [],
        })

    async def generate_stream(self, messages: list[LLMMessage]):
        yield await self.generate(messages)


def setup_user_and_workspace(client: TestClient, prefix: str = "appr_sec"):
    email = f"{prefix}_{uuid4().hex[:8]}@example.com"
    pwd = "SecurePassword123!"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pwd, "full_name": f"User {prefix}"},
    )
    assert reg.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": pwd},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    ws_res = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": f"{prefix} Workspace", "description": "Verification Workspace"},
    )
    assert ws_res.status_code == 201
    return reg.json(), token, ws_res.json()


def create_pending_approval_run(client: TestClient, token: str, ws_id: str, title: str, content: str) -> dict:
    scripted = [
        json.dumps({
            "action": "call_tool",
            "tool_name": "create_workspace_document",
            "reason": "Need approval for write",
            "arguments": {"title": title, "content": content},
        }),
        json.dumps({
            "action": "final_answer",
            "answer": "Document successfully created.",
            "citations": [],
        }),
    ]
    mock_llm = ScriptedLLM(scripted)
    app.dependency_overrides[get_ollama_llm_provider] = lambda: mock_llm

    res = client.post(
        "/api/v1/agent/runs",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws_id},
        json={"goal": f"Create document {title}"},
    )
    assert res.status_code == 201
    return res.json()


# =========================================================================
# 1. Concurrent Approvals Race Condition (Atomic DB Conditional Update)
# =========================================================================
@pytest.mark.anyio
async def test_concurrent_approvals_race_condition(client: TestClient):
    """Two concurrent transactions attempting to claim the same pending approval.

    The database conditional update MUST ensure exactly one claim succeeds,
    and the other returns False (preventing duplicate tool execution).
    """
    _user, token, ws = setup_user_and_workspace(client, "race_user")
    doc_title = f"Concurrent Note {uuid4().hex[:8]}"
    run_data = create_pending_approval_run(client, token, ws["id"], doc_title, "Concurrent test content")
    
    approval_id = run_data["pending_approval"]["id"]
    assert approval_id is not None

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = UUID(_user["id"])

    async def attempt_claim(worker_id: int):
        async with session_factory() as session:
            return await agent_repo.claim_approval_decision(
                session,
                approval_id=approval_id,
                decision=ApprovalStatus.APPROVED,
                decided_by=user_id,
                reason=f"Concurrent worker {worker_id}",
            )

    # Execute both claims concurrently against PostgreSQL
    results = await asyncio.gather(attempt_claim(1), attempt_claim(2))
    await engine.dispose()

    # Exactly one claim must return True, the other MUST return False
    assert results.count(True) == 1, f"Expected exactly one claim to succeed, got {results}"
    assert results.count(False) == 1, f"Expected exactly one claim to fail, got {results}"


# =========================================================================
# 2. Approval Payload Tampering Detection
# =========================================================================
@pytest.mark.anyio
async def test_tampered_approval_payload_rejected(client: TestClient):
    """If the approval payload is tampered in the database before approval, it must be rejected."""
    _user, token, ws = setup_user_and_workspace(client, "tamper_user")
    doc_title = f"Original Title {uuid4().hex[:8]}"
    run_data = create_pending_approval_run(client, token, ws["id"], doc_title, "Original safe content")

    approval_id = run_data["pending_approval"]["id"]

    # Tamper the payload in DB directly: change title to a hijacked value
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        res = await conn.execute(
            text("SELECT payload FROM agent_approval_requests WHERE id = :id"),
            {"id": approval_id},
        )
        payload = dict(res.scalar_one())
        payload["arguments"]["title"] = "HIJACKED_TITLE_INJECTION"
        await conn.execute(
            text("UPDATE agent_approval_requests SET payload = :p WHERE id = :id"),
            {"p": json.dumps(payload), "id": approval_id},
        )
    await engine.dispose()

    # Now attempt to approve the tampered request
    approve_res = client.post(
        f"/api/v1/agent/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
        json={"reason": "Attempting approval on tampered payload"},
    )
    # The approval execution detects payload hash mismatch and sets step status to failed
    assert approve_res.status_code == 200
    run_after = approve_res.json()
    step_result = run_after["steps"][0]
    assert step_result["status"] in ["failed", "denied"]
    assert "payload" in str(step_result).lower() or "tamper" in str(step_result).lower() or "error" in str(step_result).lower()

    # Verify no document with the hijacked title was created
    docs_res = client.get(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
    )
    docs = docs_res.json()["items"]
    assert not any(d["title"] == "HIJACKED_TITLE_INJECTION" for d in docs)


# =========================================================================
# 3. Exact Approved Payload Execution
# =========================================================================
def test_exact_approved_payload_execution(client: TestClient):
    """The document created must strictly match the approved arguments."""
    _user, token, ws = setup_user_and_workspace(client, "exact_user")
    unique_title = f"Exact Approved Note {uuid4().hex[:8]}"
    unique_content = f"Exact approved payload content {uuid4()}"
    run_data = create_pending_approval_run(client, token, ws["id"], unique_title, unique_content)

    approval_id = run_data["pending_approval"]["id"]

    approve_res = client.post(
        f"/api/v1/agent/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
        json={"reason": "Approved valid payload"},
    )
    assert approve_res.status_code == 200

    docs_res = client.get(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
    )
    docs = docs_res.json()["items"]
    matched = [d for d in docs if d["title"] == unique_title]
    assert len(matched) == 1
    doc_id = matched[0]["id"]

    # Read back document details
    detail_res = client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
    )
    assert detail_res.status_code == 200
    doc_detail = detail_res.json()
    assert doc_detail["title"] == unique_title
    assert doc_detail["content"] == unique_content


# =========================================================================
# 4. Expired Approval Cannot Be Executed
# =========================================================================
@pytest.mark.anyio
async def test_expired_approval_rejected(client: TestClient):
    """Approvals that have passed their expiration timestamp cannot be approved."""
    _user, token, ws = setup_user_and_workspace(client, "expired_user")
    doc_title = f"Expired Note {uuid4().hex[:8]}"
    run_data = create_pending_approval_run(client, token, ws["id"], doc_title, "Content for expired test")

    approval_id = run_data["pending_approval"]["id"]

    # Expire the approval in the database
    past_time = datetime.now(UTC) - timedelta(minutes=10)
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE agent_approval_requests SET expires_at = :exp WHERE id = :id"),
            {"exp": past_time, "id": approval_id},
        )
    await engine.dispose()

    # Attempt to approve
    approve_res = client.post(
        f"/api/v1/agent/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
        json={"reason": "Late approval attempt"},
    )
    assert approve_res.status_code == 400
    assert "approval_expired" in approve_res.json()["detail"] or "already" in approve_res.json()["detail"]

    # Verify no document was created
    docs_res = client.get(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
    )
    docs = docs_res.json()["items"]
    assert not any(d["title"] == doc_title for d in docs)


# =========================================================================
# 5. Cross-Workspace Approval Attempt Rejected
# =========================================================================
def test_cross_workspace_approval_rejected(client: TestClient):
    """An approval request from Workspace A cannot be approved using Workspace B context."""
    _user1, token1, ws_a = setup_user_and_workspace(client, "user_wsa")
    _user2, token2, ws_b = setup_user_and_workspace(client, "user_wsb")

    doc_title = f"Workspace A Note {uuid4().hex[:8]}"
    run_data = create_pending_approval_run(client, token1, ws_a["id"], doc_title, "WS A confidential content")
    approval_id = run_data["pending_approval"]["id"]

    # Attempt to approve using User 2 and Workspace B
    cross_res = client.post(
        f"/api/v1/agent/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {token2}", "X-Workspace-Id": ws_b["id"]},
        json={"reason": "Cross-workspace approval attack"},
    )
    assert cross_res.status_code in [400, 404]
    assert "not found" in cross_res.json()["detail"].lower()

    # Even if User 1 attempts with Workspace B header
    cross_res2 = client.post(
        f"/api/v1/agent/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {token1}", "X-Workspace-Id": ws_b["id"]},
        json={"reason": "Cross-workspace header attack"},
    )
    assert cross_res2.status_code in [403, 404]


# =========================================================================
# 6. Replayed Approval After Completion
# =========================================================================
def test_replayed_approval_prevented_and_idempotent(client: TestClient):
    """Once approved, any retry or replayed approval request must be rejected without creating duplicates."""
    _user, token, ws = setup_user_and_workspace(client, "replay_idemp")
    doc_title = f"Idempotent Note {uuid4().hex[:8]}"
    run_data = create_pending_approval_run(client, token, ws["id"], doc_title, "Single execution content")
    approval_id = run_data["pending_approval"]["id"]

    # First approval -> 200 OK
    appr1 = client.post(
        f"/api/v1/agent/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
        json={"reason": "First legitimate approval"},
    )
    assert appr1.status_code == 200

    # Second approval (Replay / Retry) -> 400 Bad Request
    appr2 = client.post(
        f"/api/v1/agent/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
        json={"reason": "Replayed approval"},
    )
    assert appr2.status_code == 400
    assert "invalid_approval_status" in appr2.json()["detail"]

    # Third approval with reject -> 400 Bad Request
    appr3 = client.post(
        f"/api/v1/agent/approvals/{approval_id}/reject",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
        json={"reason": "Reject after approved"},
    )
    assert appr3.status_code == 400

    # Verify strictly 1 document in database
    docs_res = client.get(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
    )
    matched = [d for d in docs_res.json()["items"] if d["title"] == doc_title]
    assert len(matched) == 1
