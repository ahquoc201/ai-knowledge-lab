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
            "full_name": "Document Test User",
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


def test_document_creation_and_user_isolation(client: TestClient):
    password = "TestPassword123!"

    user_a_email = f"user-a-{uuid4()}@example.com"
    user_b_email = f"user-b-{uuid4()}@example.com"

    user_a_token = register_and_login(
        client,
        email=user_a_email,
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=user_b_email,
        password=password,
    )

    user_a_headers = {
        "Authorization": f"Bearer {user_a_token}",
    }

    user_b_headers = {
        "Authorization": f"Bearer {user_b_token}",
    }

    create_response = client.post(
        "/api/v1/documents",
        headers=user_a_headers,
        json={
            "title": "User A document",
            "content": "Private knowledge belonging to User A.",
            "source_type": "text",
        },
    )

    assert create_response.status_code == 201

    created_document = create_response.json()

    assert created_document["title"] == "User A document"
    assert created_document["status"] == "pending"

    user_a_documents = client.get(
        "/api/v1/documents",
        headers=user_a_headers,
    )

    assert user_a_documents.status_code == 200
    assert any(
        document["id"] == created_document["id"]
        for document in user_a_documents.json()
    )

    user_b_documents = client.get(
        "/api/v1/documents",
        headers=user_b_headers,
    )

    assert user_b_documents.status_code == 200
    assert all(
        document["id"] != created_document["id"]
        for document in user_b_documents.json()
    )

    user_a_get_response = client.get(
        f"/api/v1/documents/{created_document['id']}",
        headers=user_a_headers,
    )

    assert user_a_get_response.status_code == 200
    assert user_a_get_response.json()["id"] == created_document["id"]

    user_b_get_response = client.get(
        f"/api/v1/documents/{created_document['id']}",
        headers=user_b_headers,
    )

    assert user_b_get_response.status_code == 404
    assert user_b_get_response.json() == {
        "detail": "Document not found",
    }

def test_delete_document_and_user_isolation(
    client: TestClient,
):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"document-delete-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"document-delete-b-{uuid4()}@example.com",
        password=password,
    )

    user_a_headers = {
        "Authorization": f"Bearer {user_a_token}",
    }

    user_b_headers = {
        "Authorization": f"Bearer {user_b_token}",
    }

    create_response = client.post(
        "/api/v1/documents",
        headers=user_a_headers,
        json={
            "title": "Document to delete",
            "content": "This document will be deleted.",
            "source_type": "text",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    user_b_delete_response = client.delete(
        f"/api/v1/documents/{document_id}",
        headers=user_b_headers,
    )

    assert user_b_delete_response.status_code == 404
    assert user_b_delete_response.json() == {
        "detail": "Document not found",
    }

    owner_get_response = client.get(
        f"/api/v1/documents/{document_id}",
        headers=user_a_headers,
    )

    assert owner_get_response.status_code == 200

    delete_response = client.delete(
        f"/api/v1/documents/{document_id}",
        headers=user_a_headers,
    )

    assert delete_response.status_code == 204
    assert delete_response.content == b""

    deleted_get_response = client.get(
        f"/api/v1/documents/{document_id}",
        headers=user_a_headers,
    )

    assert deleted_get_response.status_code == 404
    assert deleted_get_response.json() == {
        "detail": "Document not found",
    }