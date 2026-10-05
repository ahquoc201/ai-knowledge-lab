from types import SimpleNamespace
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
            "full_name": "Conversation Test User",
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


def test_conversation_creation_listing_detail_and_user_isolation(
    client: TestClient,
):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"conversation-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"conversation-b-{uuid4()}@example.com",
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
            "title": "My first conversation",
        },
    )

    assert create_response.status_code == 201

    conversation = create_response.json()

    assert conversation["title"] == "My first conversation"
    assert conversation["id"]
    assert conversation["user_id"]

    user_a_list_response = client.get(
        "/api/v1/conversations",
        headers=user_a_headers,
    )

    assert user_a_list_response.status_code == 200
    assert any(
        item["id"] == conversation["id"]
        for item in user_a_list_response.json()
    )

    user_b_list_response = client.get(
        "/api/v1/conversations",
        headers=user_b_headers,
    )

    assert user_b_list_response.status_code == 200
    assert all(
        item["id"] != conversation["id"]
        for item in user_b_list_response.json()
    )

    user_a_detail_response = client.get(
        f"/api/v1/conversations/{conversation['id']}",
        headers=user_a_headers,
    )

    assert user_a_detail_response.status_code == 200

    detail = user_a_detail_response.json()

    assert detail["id"] == conversation["id"]
    assert detail["messages"] == []

    user_b_detail_response = client.get(
        f"/api/v1/conversations/{conversation['id']}",
        headers=user_b_headers,
    )

    assert user_b_detail_response.status_code == 404
    assert user_b_detail_response.json() == {
        "detail": "Conversation not found",
    }

def test_update_conversation_and_user_isolation(
    client: TestClient,
):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"conversation-update-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"conversation-update-b-{uuid4()}@example.com",
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
            "title": "Old title",
        },
    )

    assert create_response.status_code == 201

    conversation_id = create_response.json()["id"]

    user_b_update_response = client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=user_b_headers,
        json={
            "title": "Hacked title",
        },
    )

    assert user_b_update_response.status_code == 404

    update_response = client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=user_a_headers,
        json={
            "title": "New title",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["title"] == "New title"

    detail_response = client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=user_a_headers,
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["title"] == "New title"


def test_delete_conversation_cascades_messages_and_enforces_ownership(
    client: TestClient,
    monkeypatch,
):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"conversation-delete-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"conversation-delete-b-{uuid4()}@example.com",
        password=password,
    )

    user_a_headers = {
        "Authorization": f"Bearer {user_a_token}",
    }

    user_b_headers = {
        "Authorization": f"Bearer {user_b_token}",
    }

    async def fake_answer_with_rag(*args, **kwargs):
        return SimpleNamespace(
            answer="Fake assistant answer",
            sources=[],
        )

    monkeypatch.setattr(
        "app.api.v1.rag.answer_with_rag",
        fake_answer_with_rag,
    )

    app.dependency_overrides[get_ollama_llm_provider] = (
        lambda: FakeLLMProvider()
    )

    try:
        rag_response = client.post(
            "/api/v1/rag/ask",
            headers=user_a_headers,
            json={
                "query": "Create conversation with messages",
            },
        )

        assert rag_response.status_code == 200

        conversation_id = rag_response.json()["conversation_id"]

        detail_response = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=user_a_headers,
        )

        assert detail_response.status_code == 200
        assert len(detail_response.json()["messages"]) == 2

        user_b_delete_response = client.delete(
            f"/api/v1/conversations/{conversation_id}",
            headers=user_b_headers,
        )

        assert user_b_delete_response.status_code == 404

        delete_response = client.delete(
            f"/api/v1/conversations/{conversation_id}",
            headers=user_a_headers,
        )

        assert delete_response.status_code == 204
        assert delete_response.content == b""

        deleted_detail_response = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=user_a_headers,
        )

        assert deleted_detail_response.status_code == 404
    finally:
        app.dependency_overrides.clear()