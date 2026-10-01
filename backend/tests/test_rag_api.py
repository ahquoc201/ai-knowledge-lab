from uuid import uuid4

from fastapi.testclient import TestClient

from app.llm.ollama import get_ollama_llm_provider
from app.main import app
from tests.fakes import FakeLLMProvider


def register_and_login(
    client: TestClient,
    *,
    email: str,
    password: str,
) -> str:
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "RAG API Test User",
        },
    )

    assert register_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert login_response.status_code == 200

    return login_response.json()["access_token"]


def test_rag_api_returns_answer_and_sources(
    client: TestClient,
):
    fake_llm = FakeLLMProvider(
        response=(
            "PostgreSQL hỗ trợ lưu trữ dữ liệu "
            "và transaction [Source 1]."
        ),
    )

    app.dependency_overrides[get_ollama_llm_provider] = (
        lambda: fake_llm
    )

    try:
        token = register_and_login(
            client,
            email=f"rag-api-{uuid4()}@example.com",
            password="TestPassword123!",
        )

        headers = {
            "Authorization": f"Bearer {token}",
        }

        document_response = client.post(
            "/api/v1/documents",
            headers=headers,
            json={
                "title": "PostgreSQL knowledge",
                "content": (
                    "PostgreSQL là hệ quản trị cơ sở dữ liệu "
                    "quan hệ. Nó hỗ trợ SQL và transaction."
                ),
                "source_type": "text",
            },
        )

        assert document_response.status_code == 201

        document_id = document_response.json()["id"]

        chunk_response = client.post(
            f"/api/v1/documents/{document_id}/chunks",
            headers=headers,
            json={
                "chunk_size": 1000,
                "overlap": 0,
            },
        )

        assert chunk_response.status_code == 200

        embedding_response = client.post(
            f"/api/v1/documents/{document_id}/embeddings",
            headers=headers,
        )

        assert embedding_response.status_code == 200

        rag_response = client.post(
            "/api/v1/rag/ask",
            headers=headers,
            json={
                "query": "PostgreSQL dùng để làm gì?",
                "limit": 5,
            },
        )

        assert rag_response.status_code == 200

        data = rag_response.json()

        assert data["answer"] == (
            "PostgreSQL hỗ trợ lưu trữ dữ liệu "
            "và transaction [Source 1]."
        )

        assert len(data["sources"]) >= 1
        assert data["sources"][0]["document_id"] == document_id
        assert data["sources"][0]["source_index"] == 1

        assert len(fake_llm.received_messages) == 2
        assert "[Source 1]" in fake_llm.received_messages[1].content
        assert (
            "PostgreSQL dùng để làm gì?"
            in fake_llm.received_messages[1].content
        )
    finally:
        app.dependency_overrides.clear()