"""T260039: end-to-end product journey and MVP blocker regressions.

Runs against the real FastAPI app, the configured (isolated) PostgreSQL/pgvector database,
the real ingestion task and the real embedding model. Only LLM generation is replaced by
in-process fakes (clearly named below) so answers are deterministic.
"""

import asyncio
import json
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.llm.base import LLMMessage
from app.llm.ollama import get_ollama_llm_provider
from app.schemas.rag import RAGRequest
from app.services.rag_stream import LLM_UNAVAILABLE_MESSAGE
from app.tasks.ingestion import _process_document_task

PASSWORD = "TestPassword123!"
POLICY_TEXT = (
    "Chính sách nghỉ phép Lumora 2026.\n"
    "Nhân viên chính thức được hưởng 18 ngày nghỉ phép có lương mỗi năm.\n"
    "Đơn xin nghỉ phải gửi qua hệ thống HRM Orchid trước ít nhất 7 ngày làm việc.\n"
)


class FakeGroundedLLM:
    """MOCK LLM: always answers from Source 1 with a canonical citation."""

    model = "fake-grounded"

    async def generate(self, messages: list[LLMMessage]) -> str:
        return "Nhân viên được hưởng 18 ngày nghỉ phép mỗi năm [Source 1]."

    async def generate_stream(self, messages: list[LLMMessage]):
        for token in ["Nhân viên được hưởng ", "18 ngày nghỉ phép ", "mỗi năm [Source 1]."]:
            yield token


class FailingLLM:
    """MOCK LLM: simulates an unreachable / timed-out Ollama backend."""

    model = "fake-failing"

    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def generate(self, messages: list[LLMMessage]) -> str:
        raise self.exc

    async def generate_stream(self, messages: list[LLMMessage]):
        raise self.exc
        yield  # pragma: no cover


def _register_and_login(client: TestClient, prefix: str) -> tuple[str, str]:
    email = f"{prefix}-{uuid4()}@example.com"
    res = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert res.status_code == 201
    res = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200
    return email, res.json()["access_token"]


def _headers(token: str, workspace_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if workspace_id:
        headers["X-Workspace-Id"] = workspace_id
    return headers


def _create_workspace(client: TestClient, token: str) -> str:
    res = client.post("/api/v1/workspaces", headers=_headers(token), json={"name": f"WS {uuid4().hex[:6]}"})
    assert res.status_code == 201
    return res.json()["id"]


def _upload_and_ingest(client: TestClient, token: str, workspace_id: str) -> dict:
    res = client.post(
        "/api/v1/documents/upload",
        headers=_headers(token, workspace_id),
        files={"file": ("lumora-policy.txt", POLICY_TEXT.encode(), "text/plain")},
    )
    assert res.status_code == 201
    doc = res.json()
    assert doc["status"] == "pending"

    # Run the real background task body (the Celery broker is replaced by a direct call).
    asyncio.run(_process_document_task(document_id=UUID(doc["id"]), user_id=UUID(doc["user_id"])))

    res = client.get(f"/api/v1/documents/{doc['id']}", headers=_headers(token, workspace_id))
    assert res.status_code == 200
    assert res.json()["status"] == "ready", res.json().get("error_message")
    return res.json()


def _sse_events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


@pytest.fixture
def llm_override(client: TestClient):
    def _set(llm) -> None:
        client.app.dependency_overrides[get_ollama_llm_provider] = lambda: llm

    yield _set
    client.app.dependency_overrides.pop(get_ollama_llm_provider, None)


def test_defaults_keep_dense_retrieval_and_reranking_opt_in():
    request = RAGRequest(query="q")
    assert request.retrieval_mode == "dense"
    assert request.enable_reranking is False
    assert get_settings().reranker_enabled is False


def test_full_journey_upload_ingest_ask_and_verify_citations(client: TestClient, llm_override):
    _, token = _register_and_login(client, "journey")
    ws = _create_workspace(client, token)
    doc = _upload_and_ingest(client, token, ws)

    chunks = client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=_headers(token, ws))
    assert chunks.status_code == 200
    chunk_ids = {c["id"] for c in chunks.json()}
    assert chunk_ids

    llm_override(FakeGroundedLLM())

    ask = client.post("/api/v1/rag/ask", headers=_headers(token, ws), json={"query": "Nhân viên có bao nhiêu ngày nghỉ phép?"})
    assert ask.status_code == 200
    body = ask.json()
    assert "[Source 1]" in body["answer"]
    cited = next(s for s in body["sources"] if s["source_index"] == 1)
    assert cited["document_id"] == doc["id"]
    assert cited["chunk_id"] in chunk_ids
    assert "18 ngày nghỉ phép" in cited["content"]

    stream = client.post(
        "/api/v1/rag/ask/stream",
        headers=_headers(token, ws),
        json={"query": "Nhân viên có bao nhiêu ngày nghỉ phép?", "conversation_id": body["conversation_id"]},
    )
    assert stream.status_code == 200
    events = _sse_events(stream.text)
    names = [e["event"] for e in events]
    assert names[0] == "retrieval_started"
    assert "error" not in names
    done = events[-1]
    assert done["event"] == "answer_completed"
    assert done["message_id"]
    assert done["sources"][0]["document_id"] == doc["id"]

    conversation = client.get(f"/api/v1/conversations/{body['conversation_id']}", headers=_headers(token, ws))
    assert conversation.status_code == 200
    assert [m["role"] for m in conversation.json()["messages"]] == ["user", "assistant", "user", "assistant"]


def test_rag_ask_returns_503_with_clear_message_when_llm_unavailable(client: TestClient, llm_override):
    _, token = _register_and_login(client, "llm-down")
    ws = _create_workspace(client, token)
    _upload_and_ingest(client, token, ws)

    for exc in (httpx.ReadTimeout("timed out"), httpx.ConnectError("connection refused to http://llm.internal:11434")):
        llm_override(FailingLLM(exc))
        res = client.post("/api/v1/rag/ask", headers=_headers(token, ws), json={"query": "Nhân viên có bao nhiêu ngày nghỉ phép?"})
        assert res.status_code == 503
        assert res.json() == {"detail": LLM_UNAVAILABLE_MESSAGE}
        assert res.headers.get("retry-after") == "5"

    # The API keeps serving requests afterwards.
    llm_override(FakeGroundedLLM())
    res = client.post("/api/v1/rag/ask", headers=_headers(token, ws), json={"query": "Nhân viên có bao nhiêu ngày nghỉ phép?"})
    assert res.status_code == 200


def test_rag_stream_reports_understandable_error_without_leaking_internals(client: TestClient, llm_override):
    _, token = _register_and_login(client, "stream-down")
    ws = _create_workspace(client, token)
    _upload_and_ingest(client, token, ws)

    llm_override(FailingLLM(httpx.ConnectError("connection refused to http://llm.internal:11434")))
    res = client.post("/api/v1/rag/ask/stream", headers=_headers(token, ws), json={"query": "Nhân viên có bao nhiêu ngày nghỉ phép?"})
    assert res.status_code == 200
    events = _sse_events(res.text)
    error = events[-1]
    assert error["event"] == "error"
    assert error["code"] == "llm_unavailable"
    assert error["stage"] == "llm_generation"
    assert error["error"] == LLM_UNAVAILABLE_MESSAGE
    assert "llm.internal" not in res.text


def test_shared_workspace_member_can_open_cited_document_and_continue_streamed_conversation(
    client: TestClient, llm_override
):
    _, owner_token = _register_and_login(client, "owner")
    member_email, member_token = _register_and_login(client, "member")
    _, outsider_token = _register_and_login(client, "outsider")
    ws = _create_workspace(client, owner_token)
    doc = _upload_and_ingest(client, owner_token, ws)

    invite = client.post(
        f"/api/v1/workspaces/{ws}/invitations",
        headers=_headers(owner_token),
        json={"email": member_email, "role": "editor"},
    )
    assert invite.status_code == 201
    accept = client.post(
        "/api/v1/workspaces/invitations/accept",
        headers=_headers(member_token),
        json={"token": invite.json()["invitation_token"]},
    )
    assert accept.status_code == 200

    # Member can open the teammate's document and chunks that RAG cites.
    res = client.get(f"/api/v1/documents/{doc['id']}", headers=_headers(member_token, ws))
    assert res.status_code == 200
    assert res.json()["id"] == doc["id"]
    res = client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=_headers(member_token, ws))
    assert res.status_code == 200 and res.json()

    # Non-members stay isolated, with or without a forged workspace header.
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=_headers(outsider_token, ws)).status_code == 403
    assert client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=_headers(outsider_token, ws)).status_code == 403
    assert client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=_headers(outsider_token)).status_code == 404

    # Owner starts a conversation; the member continues it via streaming.
    llm_override(FakeGroundedLLM())
    first = client.post("/api/v1/rag/ask", headers=_headers(owner_token, ws), json={"query": "Nhân viên có bao nhiêu ngày nghỉ phép?"})
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]

    res = client.post(
        "/api/v1/rag/ask/stream",
        headers=_headers(member_token, ws),
        json={"query": "Nhân viên có bao nhiêu ngày nghỉ phép?", "conversation_id": conversation_id},
    )
    done = _sse_events(res.text)[-1]
    assert done["event"] == "answer_completed"
    assert done["message_id"] is not None

    conversation = client.get(f"/api/v1/conversations/{conversation_id}", headers=_headers(owner_token, ws))
    messages = conversation.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[-1]["id"] == done["message_id"]
