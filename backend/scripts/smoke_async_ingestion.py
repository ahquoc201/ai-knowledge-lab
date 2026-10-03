import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

POLL_INTERVAL_SECONDS = 1
TIMEOUT_SECONDS = 120


def main() -> None:
    settings = get_settings()
    storage_dir = settings.upload_storage_dir

    storage_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    files_before = set(storage_dir.iterdir())

    email = f"async-smoke-{uuid4()}@example.com"
    password = "TestPassword123!"

    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": "Async Ingestion Smoke User",
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

        upload_response = client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={
                "file": (
                    "async-knowledge.txt",
                    (
                        b"PostgreSQL supports transactions. "
                        b"FastAPI can be used to build APIs. "
                        b"Celery processes background jobs."
                    ),
                    "text/plain",
                ),
            },
        )
        upload_response.raise_for_status()

        uploaded_document = upload_response.json()
        document_id = uploaded_document["id"]

        print(
            "Upload response:",
            {
                "id": document_id,
                "status": uploaded_document["status"],
            },
        )

        deadline = time.monotonic() + TIMEOUT_SECONDS

        while time.monotonic() < deadline:
            response = client.get(
                f"/api/v1/documents/{document_id}",
                headers=headers,
            )
            response.raise_for_status()

            document = response.json()
            status = document["status"]

            print("Document status:", status)

            if status == "ready":
                break

            if status == "failed":
                raise RuntimeError(
                    "Async document ingestion failed"
                )

            time.sleep(POLL_INTERVAL_SECONDS)
        else:
            raise TimeoutError(
                "Timed out waiting for document ingestion"
            )

        while time.monotonic() < deadline:
            files_after = set(storage_dir.iterdir())

            if files_after == files_before:
                break

            time.sleep(POLL_INTERVAL_SECONDS)
        else:
            raise RuntimeError(
                "Temporary upload file was not cleaned up"
            )

        assert document["content"]
        assert document["status"] == "ready"

        print("Async ingestion smoke test passed.")
        print(
            "Document:",
            {
                "id": document["id"],
                "status": document["status"],
                "source_name": document["source_name"],
            },
        )


if __name__ == "__main__":
    main()