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
            "full_name": "Semantic Search Test User",
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


def create_and_embed_document(
    client: TestClient,
    *,
    headers: dict[str, str],
    title: str,
    content: str,
) -> str:
    create_response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": title,
            "content": content,
            "source_type": "text",
        },
    )

    assert create_response.status_code == 201

    document_id = create_response.json()["id"]

    chunk_response = client.post(
        f"/api/v1/documents/{document_id}/chunks",
        headers=headers,
        json={
            "chunk_size": 1000,
            "overlap": 0,
        },
    )

    assert chunk_response.status_code == 200
    assert len(chunk_response.json()) == 1

    embedding_response = client.post(
        f"/api/v1/documents/{document_id}/embeddings",
        headers=headers,
    )

    assert embedding_response.status_code == 200
    assert embedding_response.json()["embedded_chunks"] == 1

    return document_id


def test_semantic_search_ranking_and_user_isolation(
    client: TestClient,
):
    password = "TestPassword123!"

    user_a_token = register_and_login(
        client,
        email=f"search-a-{uuid4()}@example.com",
        password=password,
    )

    user_b_token = register_and_login(
        client,
        email=f"search-b-{uuid4()}@example.com",
        password=password,
    )

    user_a_headers = {
        "Authorization": f"Bearer {user_a_token}",
    }

    user_b_headers = {
        "Authorization": f"Bearer {user_b_token}",
    }

    database_document_id = create_and_embed_document(
        client,
        headers=user_a_headers,
        title="PostgreSQL",
        content=(
            "PostgreSQL là hệ quản trị cơ sở dữ liệu quan hệ. "
            "Nó hỗ trợ SQL, transaction và lưu trữ dữ liệu."
        ),
    )

    food_document_id = create_and_embed_document(
        client,
        headers=user_a_headers,
        title="Phở bò",
        content=(
            "Phở bò là món ăn Việt Nam với bánh phở, "
            "nước dùng và thịt bò."
        ),
    )

    private_user_b_document_id = create_and_embed_document(
        client,
        headers=user_b_headers,
        title="Private database document",
        content=(
            "PostgreSQL database SQL transaction "
            "private knowledge of user B."
        ),
    )

    search_response = client.post(
        "/api/v1/search/semantic",
        headers=user_a_headers,
        json={
            "query": "PostgreSQL dùng để lưu trữ cơ sở dữ liệu như thế nào?",
            "limit": 10,
        },
    )

    assert search_response.status_code == 200

    results = search_response.json()

    assert len(results) == 2

    assert results[0]["document_id"] == database_document_id
    assert results[0]["document_id"] != food_document_id

    assert all(
        result["document_id"] != private_user_b_document_id
        for result in results
    )

    assert results[0]["similarity"] >= results[1]["similarity"]