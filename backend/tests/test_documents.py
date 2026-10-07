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

def test_reprocess_document_and_user_isolation(
    client: TestClient,
):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"document-reprocess-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"document-reprocess-b-{uuid4()}@example.com",
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
            "title": "Document to reprocess",
            "content": "PostgreSQL is a relational database system.",
            "source_type": "text",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    user_b_response = client.post(
        f"/api/v1/documents/{document_id}/reprocess",
        headers=user_b_headers,
    )

    assert user_b_response.status_code == 404
    assert user_b_response.json() == {
        "detail": "Document not found",
    }

    reprocess_response = client.post(
        f"/api/v1/documents/{document_id}/reprocess",
        headers=user_a_headers,
    )

    assert reprocess_response.status_code == 200

    reprocessed_document = reprocess_response.json()

    assert reprocessed_document["id"] == document_id
    assert reprocessed_document["status"] == "ready"

    chunks_response = client.get(
        f"/api/v1/documents/{document_id}/chunks",
        headers=user_a_headers,
    )

    assert chunks_response.status_code == 200
    assert len(chunks_response.json()) > 0


def test_reprocess_rejects_unsupported_documents(
    client: TestClient,
):
    password = "TestPassword123!"

    token = register_and_login(
        client,
        email=f"document-reprocess-validation-{uuid4()}@example.com",
        password=password,
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    file_response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Existing file",
            "content": "Previously extracted content",
            "source_type": "file",
        },
    )

    assert file_response.status_code == 201

    file_document_id = file_response.json()["id"]

    file_reprocess_response = client.post(
        f"/api/v1/documents/{file_document_id}/reprocess",
        headers=headers,
    )

    assert file_reprocess_response.status_code == 409
    assert file_reprocess_response.json() == {
        "detail": "Only text documents can currently be reprocessed",
    }

    empty_response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Empty document",
            "content": "   ",
            "source_type": "text",
        },
    )

    assert empty_response.status_code == 201

    empty_document_id = empty_response.json()["id"]

    empty_reprocess_response = client.post(
        f"/api/v1/documents/{empty_document_id}/reprocess",
        headers=headers,
    )

    assert empty_reprocess_response.status_code == 422
    assert empty_reprocess_response.json() == {
        "detail": "Document content is empty",
    }

def test_update_document_and_user_isolation(
    client: TestClient,
):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"document-update-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"document-update-b-{uuid4()}@example.com",
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
            "title": "Original title",
            "content": "Original content",
            "source_type": "text",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    user_b_response = client.patch(
        f"/api/v1/documents/{document_id}",
        headers=user_b_headers,
        json={
            "title": "Unauthorized update",
        },
    )

    assert user_b_response.status_code == 404
    assert user_b_response.json() == {
        "detail": "Document not found",
    }

    title_response = client.patch(
        f"/api/v1/documents/{document_id}",
        headers=user_a_headers,
        json={
            "title": "Updated title",
        },
    )

    assert title_response.status_code == 200
    assert title_response.json()["title"] == "Updated title"
    assert title_response.json()["content"] == "Original content"
    assert title_response.json()["status"] == "pending"

    reprocess_response = client.post(
        f"/api/v1/documents/{document_id}/reprocess",
        headers=user_a_headers,
    )

    assert reprocess_response.status_code == 200
    assert reprocess_response.json()["status"] == "ready"

    content_response = client.patch(
        f"/api/v1/documents/{document_id}",
        headers=user_a_headers,
        json={
            "content": "Updated content for reprocessing.",
        },
    )

    assert content_response.status_code == 200
    assert content_response.json()["content"] == (
        "Updated content for reprocessing."
    )
    assert content_response.json()["status"] == "pending"


def test_update_document_validation(
    client: TestClient,
):
    password = "TestPassword123!"

    token = register_and_login(
        client,
        email=f"document-update-validation-{uuid4()}@example.com",
        password=password,
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    file_response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Uploaded file",
            "content": "Extracted content",
            "source_type": "file",
        },
    )

    assert file_response.status_code == 201

    file_document_id = file_response.json()["id"]

    file_update_response = client.patch(
        f"/api/v1/documents/{file_document_id}",
        headers=headers,
        json={
            "content": "Changed content",
        },
    )

    assert file_update_response.status_code == 409
    assert file_update_response.json() == {
        "detail": "File document content cannot be updated",
    }

    text_response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Text document",
            "content": "Content",
            "source_type": "text",
        },
    )

    assert text_response.status_code == 201

    text_document_id = text_response.json()["id"]

    null_title_response = client.patch(
        f"/api/v1/documents/{text_document_id}",
        headers=headers,
        json={
            "title": None,
        },
    )

    assert null_title_response.status_code == 422
    assert null_title_response.json() == {
        "detail": "Document title cannot be null",
    }