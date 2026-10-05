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

        first_rag_response = client.post(
            "/api/v1/rag/ask",
            headers=headers,
            json={
                "query": "PostgreSQL dùng để làm gì?",
                "limit": 5,
            },
        )

        assert first_rag_response.status_code == 200

        first_data = first_rag_response.json()

        conversation_id = first_data["conversation_id"]

        assert conversation_id

        assert first_data["answer"] == (
            "PostgreSQL hỗ trợ lưu trữ dữ liệu "
            "và transaction [Source 1]."
        )

        assert len(first_data["sources"]) >= 1
        assert (
            first_data["sources"][0]["document_id"]
            == document_id
        )
        assert first_data["sources"][0]["source_index"] == 1

        assert len(fake_llm.received_messages) == 2
        assert (
            "[Source 1]"
            in fake_llm.received_messages[1].content
        )
        assert (
            "PostgreSQL dùng để làm gì?"
            in fake_llm.received_messages[1].content
        )

        second_rag_response = client.post(
            "/api/v1/rag/ask",
            headers=headers,
            json={
                "query": "Nó hỗ trợ gì?",
                "limit": 5,
                "conversation_id": conversation_id,
            },
        )

        assert second_rag_response.status_code == 200

        second_data = second_rag_response.json()

        assert second_data["conversation_id"] == conversation_id

        assert (
            "user: PostgreSQL dùng để làm gì?"
            in fake_llm.received_messages[1].content
        )

        assert (
            "assistant: PostgreSQL hỗ trợ lưu trữ dữ liệu "
            "và transaction [Source 1]."
            in fake_llm.received_messages[1].content
        )

        assert (
            "Nó hỗ trợ gì?"
            in fake_llm.received_messages[1].content
        )

        conversation_response = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers,
        )

        assert conversation_response.status_code == 200

        conversation = conversation_response.json()

        assert conversation["id"] == conversation_id
        assert (
            conversation["title"]
            == "PostgreSQL dùng để làm gì?"
        )

        messages = conversation["messages"]

        assert len(messages) == 4

        assert messages[0]["role"] == "user"
        assert (
            messages[0]["content"]
            == "PostgreSQL dùng để làm gì?"
        )

        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == (
            "PostgreSQL hỗ trợ lưu trữ dữ liệu "
            "và transaction [Source 1]."
        )

        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "Nó hỗ trợ gì?"

        assert messages[3]["role"] == "assistant"
        assert messages[3]["content"] == (
            "PostgreSQL hỗ trợ lưu trữ dữ liệu "
            "và transaction [Source 1]."
        )
    finally:
        app.dependency_overrides.clear()

def test_rag_api_rejects_other_users_conversation(
    client: TestClient,
):
    fake_llm = FakeLLMProvider()

    app.dependency_overrides[get_ollama_llm_provider] = (
        lambda: fake_llm
    )

    try:
        password = "TestPassword123!"

        user_a_token = register_and_login(
            client,
            email=f"rag-owner-a-{uuid4()}@example.com",
            password=password,
        )

        user_b_token = register_and_login(
            client,
            email=f"rag-owner-b-{uuid4()}@example.com",
            password=password,
        )

        user_a_headers = {
            "Authorization": f"Bearer {user_a_token}",
        }

        user_b_headers = {
            "Authorization": f"Bearer {user_b_token}",
        }

        create_response = client.post(
            "/api/v1/conversations",
            headers=user_a_headers,
            json={
                "title": "Private conversation",
            },
        )

        assert create_response.status_code == 201

        conversation_id = create_response.json()["id"]

        rag_response = client.post(
            "/api/v1/rag/ask",
            headers=user_b_headers,
            json={
                "query": "Cho tôi xem nội dung cuộc trò chuyện này",
                "conversation_id": conversation_id,
            },
        )

        assert rag_response.status_code == 404
        assert rag_response.json() == {
            "detail": "Conversation not found",
        }

        assert fake_llm.received_messages == []
    finally:
        app.dependency_overrides.clear()