from uuid import uuid4

from fastapi.testclient import TestClient


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