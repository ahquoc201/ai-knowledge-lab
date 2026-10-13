import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.llm.ollama import get_ollama_llm_provider
from app.main import app
from app.models.message import Message
from app.models.user import User
from app.services.context_builder import ContextSource, RetrievalContext
from app.services.rag_prompt import INSUFFICIENT_CONTEXT_ANSWER
from app.services.rag_stream import (
    UNVERIFIED_CITATION_ANSWER,
    answer_with_rag_stream,
)
from tests.fakes import FakeLLMProvider


def parse_sse_events(raw_stream: str) -> list[dict]:
    """Parse raw SSE text into list of dict events."""
    events = []
    lines = raw_stream.strip().split("\n\n")
    for block in lines:
        if not block.strip():
            continue
        data_line = None
        for line in block.split("\n"):
            if line.startswith("data: "):
                data_line = line[6:]
                break
        if data_line:
            try:
                events.append(json.loads(data_line))
            except json.JSONDecodeError:
                pass
    return events


@pytest.mark.anyio
async def test_rag_stream_lifecycle_success(monkeypatch):
    """Test full streaming lifecycle with valid citations."""
    user = User(id=uuid4(), email="user@example.com")
    conversation_id = uuid4()
    query = "What is PostgreSQL?"

    chunk_id = uuid4()
    doc_id = uuid4()
    source = ContextSource(
        source_index=1,
        document_id=doc_id,
        chunk_id=chunk_id,
        chunk_index=0,
        content="PostgreSQL is an open-source database system.",
        similarity=0.95,
        document_title="PostgreSQL Guide",
        char_start=0,
        char_end=45,
    )
    fake_context = RetrievalContext(
        text="[Source 1]\nPostgreSQL is an open-source database system.",
        sources=[source],
    )

    async def fake_retrieve_context(*args, **kwargs):
        return fake_context

    monkeypatch.setattr(
        "app.services.rag_stream.retrieve_context",
        fake_retrieve_context,
    )

    saved_messages = []

    async def fake_create_conversation_message(
        session, *, user, conversation_id, role, content
    ):
        msg = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        saved_messages.append(msg)
        return msg

    monkeypatch.setattr(
        "app.services.rag_stream.create_conversation_message",
        fake_create_conversation_message,
    )

    saved_sources = []

    async def fake_save_assistant_message_sources(session, *, message, sources):
        saved_sources.extend(sources)
        return sources

    monkeypatch.setattr(
        "app.services.rag_stream.save_assistant_message_sources",
        fake_save_assistant_message_sources,
    )

    fake_llm = FakeLLMProvider(
        stream_chunks=["PostgreSQL ", "is a database [Source 1]."]
    )

    chunks = []
    async for chunk in answer_with_rag_stream(
        None,
        user=user,
        conversation_id=conversation_id,
        query=query,
        llm=fake_llm,
    ):
        chunks.append(chunk)

    raw_output = "".join(chunks)
    events = parse_sse_events(raw_output)

    event_types = [e["event"] for e in events]
    assert "retrieval_started" in event_types
    assert "retrieval_completed" in event_types
    assert "generation_started" in event_types
    assert "token" in event_types
    assert "answer_completed" in event_types

    # Verify retrieval completed sources
    retrieval_evt = next(e for e in events if e["event"] == "retrieval_completed")
    assert len(retrieval_evt["sources"]) == 1
    assert retrieval_evt["sources"][0]["document_title"] == "PostgreSQL Guide"

    # Verify completion
    completed_evt = next(e for e in events if e["event"] == "answer_completed")
    assert completed_evt["answer"] == "PostgreSQL is a database [Source 1]."
    assert len(completed_evt["sources"]) == 1
    assert str(conversation_id) == completed_evt["conversation_id"]

    # Verify persistence
    assert len(saved_messages) == 1
    assert saved_messages[0].content == "PostgreSQL is a database [Source 1]."
    assert len(saved_sources) == 1


@pytest.mark.anyio
async def test_rag_stream_refusal_when_no_context(monkeypatch):
    """When retrieval has no evidence, stream refusal without LLM call."""
    user = User(id=uuid4(), email="user@example.com")
    conversation_id = uuid4()
    query = "Unknown question"

    empty_context = RetrievalContext(text="", sources=[])

    async def fake_retrieve_context(*args, **kwargs):
        return empty_context

    monkeypatch.setattr(
        "app.services.rag_stream.retrieve_context",
        fake_retrieve_context,
    )

    saved_messages = []

    async def fake_create_conversation_message(
        session, *, user, conversation_id, role, content
    ):
        msg = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        saved_messages.append(msg)
        return msg

    monkeypatch.setattr(
        "app.services.rag_stream.create_conversation_message",
        fake_create_conversation_message,
    )

    fake_llm = FakeLLMProvider(response="Should not be called")

    chunks = []
    async for chunk in answer_with_rag_stream(
        None,
        user=user,
        conversation_id=conversation_id,
        query=query,
        llm=fake_llm,
    ):
        chunks.append(chunk)

    raw_output = "".join(chunks)
    events = parse_sse_events(raw_output)

    event_types = [e["event"] for e in events]
    assert "generation_started" not in event_types
    assert fake_llm.received_messages == []

    completed_evt = next(e for e in events if e["event"] == "answer_completed")
    assert completed_evt["answer"] == INSUFFICIENT_CONTEXT_ANSWER
    assert completed_evt["sources"] == []


@pytest.mark.anyio
async def test_rag_stream_invalid_citations_overridden(monkeypatch):
    """When stream finishes with missing citations, completed event overrides with refusal."""
    user = User(id=uuid4(), email="user@example.com")
    conversation_id = uuid4()
    query = "What is PostgreSQL?"

    source = ContextSource(
        source_index=1,
        document_id=uuid4(),
        chunk_id=uuid4(),
        chunk_index=0,
        content="PostgreSQL content.",
        similarity=0.9,
    )
    fake_context = RetrievalContext(
        text="[Source 1]\nPostgreSQL content.",
        sources=[source],
    )

    async def fake_retrieve_context(*args, **kwargs):
        return fake_context

    monkeypatch.setattr(
        "app.services.rag_stream.retrieve_context",
        fake_retrieve_context,
    )

    saved_messages = []

    async def fake_create_conversation_message(
        session, *, user, conversation_id, role, content
    ):
        msg = Message(
            id=uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        saved_messages.append(msg)
        return msg

    monkeypatch.setattr(
        "app.services.rag_stream.create_conversation_message",
        fake_create_conversation_message,
    )

    # Missing [Source 1] citation
    fake_llm = FakeLLMProvider(
        stream_chunks=["PostgreSQL is a great database without citations."]
    )

    chunks = []
    async for chunk in answer_with_rag_stream(
        None,
        user=user,
        conversation_id=conversation_id,
        query=query,
        llm=fake_llm,
    ):
        chunks.append(chunk)

    raw_output = "".join(chunks)
    events = parse_sse_events(raw_output)

    completed_evt = next(e for e in events if e["event"] == "answer_completed")
    assert completed_evt["answer"] == UNVERIFIED_CITATION_ANSWER
    assert completed_evt["sources"] == []

    # Verified refusal persisted in DB
    assert len(saved_messages) == 1
    assert saved_messages[0].content == UNVERIFIED_CITATION_ANSWER


def test_rag_stream_api_endpoint(client: TestClient, monkeypatch):
    """Test POST /api/v1/rag/ask/stream returns SSE and proper lifecycle."""
    doc_id = uuid4()
    chunk_id = uuid4()
    source = ContextSource(
        source_index=1,
        document_id=doc_id,
        chunk_id=chunk_id,
        chunk_index=0,
        content="PostgreSQL is an ACID compliant DB.",
        similarity=0.92,
        document_title="PG Overview",
    )
    fake_context = RetrievalContext(
        text="[Source 1]\nPostgreSQL is an ACID compliant DB.",
        sources=[source],
    )

    async def fake_retrieve_context(*args, **kwargs):
        return fake_context

    monkeypatch.setattr(
        "app.services.rag_stream.retrieve_context",
        fake_retrieve_context,
    )

    fake_llm = FakeLLMProvider(
        stream_chunks=["PostgreSQL ", "is ACID compliant [Source 1]."]
    )
    app.dependency_overrides[get_ollama_llm_provider] = lambda: fake_llm

    try:
        email = f"rag-stream-{uuid4()}@example.com"
        password = "TestPassword123!"

        reg_res = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "Stream User"},
        )
        assert reg_res.status_code == 201

        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        response = client.post(
            "/api/v1/rag/ask/stream",
            json={"query": "Tell me about PostgreSQL"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert "x-conversation-id" in response.headers

        events = parse_sse_events(response.text)
        types = [e["event"] for e in events]
        assert "retrieval_started" in types
        assert "retrieval_completed" in types
        assert "generation_started" in types
        assert "token" in types
        assert "answer_completed" in types

        answer_evt = next(e for e in events if e["event"] == "answer_completed")
        assert answer_evt["answer"] == "PostgreSQL is ACID compliant [Source 1]."
        assert len(answer_evt["sources"]) == 1
        assert answer_evt["sources"][0]["document_title"] == "PG Overview"

    finally:
        app.dependency_overrides.pop(get_ollama_llm_provider, None)
