"""Integration tests for Governed Agent API lifecycle and authorization."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.agent_state import AgentRunStatus
from app.core.workspace_role import WorkspaceRole
from app.llm.base import LLMMessage, LLMProvider
from app.llm.ollama import get_ollama_llm_provider
from app.main import app


@pytest.fixture(autouse=True)
def mock_embedding_query(monkeypatch):
    monkeypatch.setattr(
        "app.services.semantic_search._embed_query",
        lambda text: [0.05] * 384,
    )


class ScriptedLLMProvider(LLMProvider):
    """Predictable LLM that yields a scripted sequence of outputs."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.call_count = 0
        self.received_messages: list[list[LLMMessage]] = []

    async def generate(self, messages: list[LLMMessage]) -> str:
        self.received_messages.append(messages)
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        # Default final answer if out of script
        return json.dumps({
            "action": "final_answer",
            "answer": "Completed task.",
            "citations": [],
        })

    async def generate_stream(self, messages: list[LLMMessage]):
        res = await self.generate(messages)
        yield res


def register_and_login(client: TestClient, prefix: str = "agent_user") -> tuple[dict, str]:
    email = f"{prefix}-{uuid4()}@example.com"
    password = "TestPassword123!"

    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": f"User {prefix}"},
    )
    assert reg.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return reg.json(), token


def create_workspace(client: TestClient, token: str, name: str) -> dict:
    res = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "description": f"Desc for {name}"},
    )
    assert res.status_code == 201
    return res.json()


def invite_member(
    client: TestClient,
    owner_token: str,
    ws_id: str,
    invitee_email: str,
    role: WorkspaceRole,
) -> None:
    res = client.post(
        f"/api/v1/workspaces/{ws_id}/invitations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": invitee_email, "role": role.value},
    )
    assert res.status_code == 201


def accept_invitations(client: TestClient, token: str) -> None:
    invs = client.get(
        "/api/v1/workspaces/invitations/pending",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    for inv in invs:
        client.post(
            f"/api/v1/workspaces/invitations/{inv['id']}/accept",
            headers={"Authorization": f"Bearer {token}"},
        )


def test_agent_run_read_tools_lifecycle(client: TestClient):
    """Agent executes search and get_document_details, then finishes with final answer."""
    _user, token = register_and_login(client, "owner")
    ws = create_workspace(client, token, "Engineering WS")

    # Upload a document
    doc_res = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
        json={"title": "Backend Architecture", "content": "Microservices with async PostgreSQL.", "source_type": "text"},
    )
    assert doc_res.status_code == 201
    doc_id = doc_res.json()["id"]

    scripted_responses = [
        # Step 1: Search documents
        json.dumps({
            "action": "call_tool",
            "tool_name": "search_workspace_documents",
            "reason": "Search for architecture docs",
            "arguments": {"query": "PostgreSQL"},
        }),
        # Step 2: Get document details
        json.dumps({
            "action": "call_tool",
            "tool_name": "get_document_details",
            "reason": "Read document details",
            "arguments": {"document_id": doc_id},
        }),
        # Step 3: Final Answer
        json.dumps({
            "action": "final_answer",
            "answer": "Kiến trúc sử dụng microservices với async PostgreSQL.",
            "citations": ["Backend Architecture"],
        }),
    ]

    mock_llm = ScriptedLLMProvider(scripted_responses)
    app.dependency_overrides[get_ollama_llm_provider] = lambda: mock_llm

    try:
        run_res = client.post(
            "/api/v1/agent/runs",
            headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
            json={"goal": "Tìm hiểu kiến trúc backend"},
        )
        assert run_res.status_code == 201
        run_data = run_res.json()
        assert run_data["status"] == AgentRunStatus.COMPLETED.value
        assert run_data["final_answer"] == "Kiến trúc sử dụng microservices với async PostgreSQL."
        assert len(run_data["steps"]) == 2
        assert run_data["steps"][0]["tool_name"] == "search_workspace_documents"
        assert run_data["steps"][0]["status"] == "succeeded"
        assert run_data["steps"][1]["tool_name"] == "get_document_details"
        assert run_data["steps"][1]["status"] == "succeeded"

        # Check events
        ev_res = client.get(
            f"/api/v1/agent/runs/{run_data['id']}/events",
            headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
        )
        assert ev_res.status_code == 200
        event_types = [e["event_type"] for e in ev_res.json()]
        assert "run_started" in event_types
        assert "step_started" in event_types
        assert "step_succeeded" in event_types
        assert "run_completed" in event_types
    finally:
        app.dependency_overrides.clear()


def test_agent_human_approval_write_lifecycle(client: TestClient):
    """Agent proposes to create a document, pauses for approval, and finishes after approval."""
    _user, token = register_and_login(client, "editor_user")
    ws = create_workspace(client, token, "Docs WS")

    scripted_responses = [
        # Step 1: Propose creating a new document
        json.dumps({
            "action": "call_tool",
            "tool_name": "create_workspace_document",
            "reason": "Save summarized backend notes",
            "arguments": {
                "title": "Backend Summary Note",
                "content": "Tổng hợp: Backend dùng FastAPI và PostgreSQL.",
            },
        }),
        # Step 2: Final answer after approval execution
        json.dumps({
            "action": "final_answer",
            "answer": "Đã tạo tài liệu ghi chú mới thành công.",
            "citations": ["Backend Summary Note"],
        }),
    ]

    mock_llm = ScriptedLLMProvider(scripted_responses)
    app.dependency_overrides[get_ollama_llm_provider] = lambda: mock_llm

    try:
        # Start run -> should pause at AWAITING_APPROVAL
        run_res = client.post(
            "/api/v1/agent/runs",
            headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
            json={"goal": "Tổng hợp và tạo tài liệu mới"},
        )
        assert run_res.status_code == 201
        run_data = run_res.json()
        assert run_data["status"] == AgentRunStatus.AWAITING_APPROVAL.value
        assert run_data["pending_approval"] is not None

        approval_id = run_data["pending_approval"]["id"]
        assert run_data["pending_approval"]["tool_name"] == "create_workspace_document"
        assert run_data["pending_approval"]["payload"]["arguments"]["title"] == "Backend Summary Note"

        # Approve the action
        approve_res = client.post(
            f"/api/v1/agent/approvals/{approval_id}/approve",
            headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
            json={"reason": "Approved by user"},
        )
        assert approve_res.status_code == 200
        completed_run = approve_res.json()
        assert completed_run["status"] == AgentRunStatus.COMPLETED.value
        assert "thành công" in completed_run["final_answer"]

        # Verify document was created in the workspace
        docs = client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
        ).json()
        doc_titles = [d["title"] for d in docs["items"]]
        assert "Backend Summary Note" in doc_titles

    finally:
        app.dependency_overrides.clear()


def test_approval_rejection_lifecycle(client: TestClient):
    """When user rejects proposed WRITE action, step is marked rejected and agent proceeds."""
    _user, token = register_and_login(client, "approver")
    ws = create_workspace(client, token, "Rejection WS")

    scripted_responses = [
        json.dumps({
            "action": "call_tool",
            "tool_name": "create_workspace_document",
            "reason": "create draft",
            "arguments": {"title": "Draft", "content": "Draft content"},
        }),
        json.dumps({
            "action": "final_answer",
            "answer": "Hành động tạo tài liệu đã bị người dùng từ chối.",
            "citations": [],
        }),
    ]

    mock_llm = ScriptedLLMProvider(scripted_responses)
    app.dependency_overrides[get_ollama_llm_provider] = lambda: mock_llm

    try:
        run_res = client.post(
            "/api/v1/agent/runs",
            headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
            json={"goal": "Tạo draft"},
        )
        assert run_res.status_code == 201
        run_data = run_res.json()
        approval_id = run_data["pending_approval"]["id"]

        # Reject the action
        reject_res = client.post(
            f"/api/v1/agent/approvals/{approval_id}/reject",
            headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
            json={"reason": "Không cần tạo tài liệu này"},
        )
        assert reject_res.status_code == 200
        res = reject_res.json()
        assert res["status"] == AgentRunStatus.COMPLETED.value
        assert "từ chối" in res["final_answer"]

        # Verify document was NOT created
        docs = client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
        ).json()
        assert not any(d["title"] == "Draft" for d in docs["items"])

    finally:
        app.dependency_overrides.clear()


def test_agent_run_cancellation(client: TestClient):
    """Run can be cancelled, transitioning to CANCELLED and canceling pending approvals."""
    _user, token = register_and_login(client, "canceller")
    ws = create_workspace(client, token, "Cancel WS")

    scripted_responses = [
        json.dumps({
            "action": "call_tool",
            "tool_name": "create_workspace_document",
            "reason": "create pending doc",
            "arguments": {"title": "Pending", "content": "Content"},
        }),
    ]

    mock_llm = ScriptedLLMProvider(scripted_responses)
    app.dependency_overrides[get_ollama_llm_provider] = lambda: mock_llm

    try:
        run_res = client.post(
            "/api/v1/agent/runs",
            headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
            json={"goal": "Pending task"},
        )
        run_data = run_res.json()
        assert run_data["status"] == AgentRunStatus.AWAITING_APPROVAL.value

        # Cancel the run
        cancel_res = client.post(
            f"/api/v1/agent/runs/{run_data['id']}/cancel",
            headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": ws["id"]},
        )
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == AgentRunStatus.CANCELLED.value

    finally:
        app.dependency_overrides.clear()
