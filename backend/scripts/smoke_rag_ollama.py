from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    email = f"rag-smoke-{uuid4()}@example.com"
    password = "TestPassword123!"

    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": "RAG Smoke User",
            },
        )
        register_response.raise_for_status()

        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "password": password,
            },
        )
        login_response.raise_for_status()

        token = login_response.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
        }

        document_response = client.post(
            "/api/v1/documents",
            headers=headers,
            json={
                "title": "PostgreSQL knowledge",
                "content": (
                    "PostgreSQL là hệ quản trị cơ sở dữ liệu quan hệ. "
                    "Nó hỗ trợ SQL, transaction và lưu trữ dữ liệu."
                ),
                "source_type": "text",
            },
        )
        document_response.raise_for_status()

        document_id = document_response.json()["id"]

        chunk_response = client.post(
            f"/api/v1/documents/{document_id}/chunks",
            headers=headers,
            json={
                "chunk_size": 1000,
                "overlap": 0,
            },
        )
        chunk_response.raise_for_status()

        embedding_response = client.post(
            f"/api/v1/documents/{document_id}/embeddings",
            headers=headers,
        )
        embedding_response.raise_for_status()

        rag_response = client.post(
            "/api/v1/rag/ask",
            headers=headers,
            json={
                "query": "PostgreSQL có hỗ trợ transaction không?",
                "limit": 3,
            },
        )
        rag_response.raise_for_status()

        print(rag_response.json())


if __name__ == "__main__":
    main()