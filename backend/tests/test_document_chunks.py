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
            "full_name": "Chunk Test User",
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


def test_document_chunking_and_user_isolation(client: TestClient):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"chunk-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"chunk-b-{uuid4()}@example.com",
        password=password,
    )

    user_a_headers = {
        "Authorization": f"Bearer {user_a_token}",
    }

    user_b_headers = {
        "Authorization": f"Bearer {user_b_token}",
    }

    create_document_response = client.post(
        "/api/v1/documents",
        headers=user_a_headers,
        json={
            "title": "Chunking test",
            "content": "abcdefghij",
            "source_type": "text",
        },
    )

    assert create_document_response.status_code == 201

    document_id = create_document_response.json()["id"]

    chunk_response = client.post(
        f"/api/v1/documents/{document_id}/chunks",
        headers=user_a_headers,
        json={
            "chunk_size": 4,
            "overlap": 1,
        },
    )

    assert chunk_response.status_code == 200

    chunks = chunk_response.json()

    embedding_response = client.post(
        f"/api/v1/documents/{document_id}/embeddings",
        headers=user_a_headers,
    )

    assert embedding_response.status_code == 200
    assert embedding_response.json() == {
        "document_id": document_id,
        "embedded_chunks": 3,
    }

    assert len(chunks) == 3

    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["content"] == "abcd"
    assert chunks[0]["char_start"] == 0
    assert chunks[0]["char_end"] == 4

    assert chunks[1]["chunk_index"] == 1
    assert chunks[1]["content"] == "defg"
    assert chunks[1]["char_start"] == 3
    assert chunks[1]["char_end"] == 7

    assert chunks[2]["chunk_index"] == 2
    assert chunks[2]["content"] == "ghij"
    assert chunks[2]["char_start"] == 6
    assert chunks[2]["char_end"] == 10

    get_response = client.get(
        f"/api/v1/documents/{document_id}/chunks",
        headers=user_a_headers,
    )

    assert get_response.status_code == 200
    assert get_response.json() == chunks

    rechunk_response = client.post(
        f"/api/v1/documents/{document_id}/chunks",
        headers=user_a_headers,
        json={
            "chunk_size": 6,
            "overlap": 0,
        },
    )

    assert rechunk_response.status_code == 200

    rechunked = rechunk_response.json()

    assert len(rechunked) == 2
    assert rechunked[0]["content"] == "abcdef"
    assert rechunked[1]["content"] == "ghij"

    reembed_response = client.post(
        f"/api/v1/documents/{document_id}/embeddings",
        headers=user_a_headers,
    )

    assert reembed_response.status_code == 200
    assert reembed_response.json() == {
        "document_id": document_id,
        "embedded_chunks": 2,
    }

    user_b_get_response = client.get(
        f"/api/v1/documents/{document_id}/chunks",
        headers=user_b_headers,
    )

    assert user_b_get_response.status_code == 404
    assert user_b_get_response.json() == {
        "detail": "Document not found",
    }

    user_b_post_response = client.post(
        f"/api/v1/documents/{document_id}/chunks",
        headers=user_b_headers,
        json={
            "chunk_size": 4,
            "overlap": 1,
        },
    )

    assert user_b_post_response.status_code == 404