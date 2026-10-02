from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.test_documents import register_and_login


def get_auth_headers(client: TestClient) -> dict[str, str]:
    token = register_and_login(
        client,
        email=f"upload-{uuid4()}@example.com",
        password="TestPassword123!",
    )

    return {
        "Authorization": f"Bearer {token}",
    }


def test_upload_txt_document_success(
    client: TestClient,
    monkeypatch,
):
    document_id = uuid4()
    now = datetime.now(UTC)

    async def fake_ingest_file(
        session,
        *,
        user,
        filename,
        data,
        mime_type,
    ):
        assert filename == "knowledge.txt"
        assert data == b"PostgreSQL supports transactions."
        assert mime_type == "text/plain"

        return SimpleNamespace(
            id=document_id,
            user_id=user.id,
            title=filename,
            source_type="file",
            source_name=filename,
            mime_type=mime_type,
            content=data.decode(),
            status="ready",
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(
        "app.api.v1.documents.ingest_file",
        fake_ingest_file,
    )

    response = client.post(
        "/api/v1/documents/upload",
        headers=get_auth_headers(client),
        files={
            "file": (
                "knowledge.txt",
                b"PostgreSQL supports transactions.",
                "text/plain",
            ),
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["id"] == str(document_id)
    assert body["title"] == "knowledge.txt"
    assert body["source_type"] == "file"
    assert body["source_name"] == "knowledge.txt"
    assert body["mime_type"] == "text/plain"
    assert body["status"] == "ready"

@pytest.mark.parametrize(
    ("filename", "data", "mime_type"),
    [
        (
            "knowledge.pdf",
            b"%PDF-1.4 fake content",
            "application/pdf",
        ),
        (
            "knowledge.docx",
            b"PK\x03\x04fake content",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ],
)
def test_upload_supported_document_types(
    client: TestClient,
    monkeypatch,
    filename: str,
    data: bytes,
    mime_type: str,
):
    document_id = uuid4()
    now = datetime.now(UTC)

    async def fake_ingest_file(
        session,
        *,
        user,
        filename,
        data,
        mime_type,
    ):
        return SimpleNamespace(
            id=document_id,
            user_id=user.id,
            title=filename,
            source_type="file",
            source_name=filename,
            mime_type=mime_type,
            content="Extracted document content",
            status="ready",
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(
        "app.api.v1.documents.ingest_file",
        fake_ingest_file,
    )

    response = client.post(
        "/api/v1/documents/upload",
        headers=get_auth_headers(client),
        files={
            "file": (
                filename,
                data,
                mime_type,
            ),
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["id"] == str(document_id)
    assert body["title"] == filename
    assert body["source_type"] == "file"
    assert body["source_name"] == filename
    assert body["mime_type"] == mime_type
    assert body["status"] == "ready"

def test_upload_rejects_unsupported_file_type(
    client: TestClient,
):
    response = client.post(
        "/api/v1/documents/upload",
        headers=get_auth_headers(client),
        files={
            "file": (
                "document.rtf",
                b"fake rtf content",
                "application/rtf",
            ),
        },
    )

    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_rejects_empty_txt(
    client: TestClient,
):
    response = client.post(
        "/api/v1/documents/upload",
        headers=get_auth_headers(client),
        files={
            "file": (
                "empty.txt",
                b"   \n\t",
                "text/plain",
            ),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Extracted text is empty"


def test_upload_rejects_file_over_size_limit(
    client: TestClient,
):
    oversized_data = b"a" * ((5 * 1024 * 1024) + 1)

    response = client.post(
        "/api/v1/documents/upload",
        headers=get_auth_headers(client),
        files={
            "file": (
                "large.txt",
                oversized_data,
                "text/plain",
            ),
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == (
        "Uploaded file exceeds the maximum allowed size"
    )