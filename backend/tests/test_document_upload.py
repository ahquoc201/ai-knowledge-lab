
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.document_status import DocumentStatus
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


def build_pending_document(
    *,
    user_id,
    filename: str,
    mime_type: str,
    storage_key: str,
):
    now = datetime.now(UTC)

    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        title=filename,
        source_type="file",
        source_name=filename,
        mime_type=mime_type,
        storage_key=storage_key,
        content=None,
        status="pending",
        created_at=now,
        updated_at=now,
    )


def test_upload_txt_document_queues_background_processing(
    client: TestClient,
    monkeypatch,
):
    stored_path = Path("/tmp/fake-knowledge.txt")
    task_delay = Mock()
    delete_file = Mock()

    monkeypatch.setattr(
        "app.api.v1.documents.save_upload_file",
        lambda *, filename, data: stored_path,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.delete_upload_file",
        delete_file,
    )

    async def fake_create_user_document(
        session,
        *,
        user,
        data,
        storage_key,
    ):
        assert data.title == "knowledge.txt"
        assert data.content is None
        assert data.source_type == "file"
        assert data.source_name == "knowledge.txt"
        assert data.mime_type == "text/plain"
        assert storage_key == stored_path.name

        return build_pending_document(
            user_id=user.id,
            filename="knowledge.txt",
            mime_type="text/plain",
            storage_key=storage_key,
        )

    monkeypatch.setattr(
        "app.api.v1.documents.create_user_document",
        fake_create_user_document,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
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

    assert body["title"] == "knowledge.txt"
    assert body["source_type"] == "file"
    assert body["source_name"] == "knowledge.txt"
    assert body["mime_type"] == "text/plain"
    assert body["content"] is None
    assert body["status"] == "pending"

    # Internal storage location must not be exposed by the API.
    assert "storage_key" not in body

    # The new Celery contract uses exactly two arguments.
    task_delay.assert_called_once_with(
        body["id"],
        body["user_id"],
    )

    delete_file.assert_not_called()


@pytest.mark.parametrize(
    ("filename", "file_data", "mime_type"),
    [
        (
            "knowledge.pdf",
            b"%PDF fake bytes",
            "application/pdf",
        ),
        (
            "knowledge.docx",
            b"PK\x03\x04fake bytes",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "knowledge.md",
            b"# Markdown knowledge\n\nContent",
            "text/markdown",
        ),
    ],
)
def test_upload_supported_document_types_are_queued(
    client: TestClient,
    monkeypatch,
    filename: str,
    file_data: bytes,
    mime_type: str,
):
    stored_path = Path(f"/tmp/{filename}")
    task_delay = Mock()

    monkeypatch.setattr(
        "app.api.v1.documents.save_upload_file",
        lambda *, filename, data: stored_path,
    )

    async def fake_create_user_document(
        session,
        *,
        user,
        data,
        storage_key,
    ):
        assert data.source_type == "file"
        assert data.source_name == filename
        assert storage_key == stored_path.name

        return build_pending_document(
            user_id=user.id,
            filename=filename,
            mime_type=mime_type,
            storage_key=storage_key,
        )

    monkeypatch.setattr(
        "app.api.v1.documents.create_user_document",
        fake_create_user_document,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

    response = client.post(
        "/api/v1/documents/upload",
        headers=get_auth_headers(client),
        files={
            "file": (
                filename,
                file_data,
                mime_type,
            ),
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["title"] == filename
    assert body["mime_type"] == mime_type
    assert body["content"] is None
    assert body["status"] == "pending"

    task_delay.assert_called_once_with(
        body["id"],
        body["user_id"],
    )


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


def test_upload_empty_txt_is_queued_for_background_processing(
    client: TestClient,
    monkeypatch,
):
    stored_path = Path("/tmp/empty.txt")
    task_delay = Mock()

    monkeypatch.setattr(
        "app.api.v1.documents.save_upload_file",
        lambda *, filename, data: stored_path,
    )

    async def fake_create_user_document(
        session,
        *,
        user,
        data,
        storage_key,
    ):
        assert storage_key == stored_path.name

        return build_pending_document(
            user_id=user.id,
            filename="empty.txt",
            mime_type="text/plain",
            storage_key=storage_key,
        )

    monkeypatch.setattr(
        "app.api.v1.documents.create_user_document",
        fake_create_user_document,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

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

    assert response.status_code == 201

    body = response.json()

    assert body["status"] == "pending"

    task_delay.assert_called_once_with(
        body["id"],
        body["user_id"],
    )


def test_upload_rejects_file_over_size_limit(
    client: TestClient,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.api.v1.documents.get_settings",
        lambda: SimpleNamespace(
            max_upload_size_bytes=10,
        ),
    )

    response = client.post(
        "/api/v1/documents/upload",
        headers=get_auth_headers(client),
        files={
            "file": (
                "large.txt",
                b"a" * 11,
                "text/plain",
            ),
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == (
        "Uploaded file exceeds the maximum allowed size"
    )


def test_upload_keeps_stored_file_when_enqueue_fails(
    client: TestClient,
    monkeypatch,
):
    stored_path = Path("/tmp/fake-failed.txt")
    delete_upload_file = Mock()
    set_document_status = AsyncMock()
    created_documents = []

    monkeypatch.setattr(
        "app.api.v1.documents.set_document_status",
        set_document_status,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.save_upload_file",
        lambda *, filename, data: stored_path,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.delete_upload_file",
        delete_upload_file,
    )

    async def fake_create_user_document(
        session,
        *,
        user,
        data,
        storage_key,
    ):
        assert storage_key == stored_path.name

        document = build_pending_document(
            user_id=user.id,
            filename="knowledge.txt",
            mime_type="text/plain",
            storage_key=storage_key,
        )

        created_documents.append(document)
        return document

    task_delay = Mock(
        side_effect=RuntimeError("Broker unavailable")
    )

    monkeypatch.setattr(
        "app.api.v1.documents.create_user_document",
        fake_create_user_document,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

    with pytest.raises(
        RuntimeError,
        match="Broker unavailable",
    ):
        client.post(
            "/api/v1/documents/upload",
            headers=get_auth_headers(client),
            files={
                "file": (
                    "knowledge.txt",
                    b"PostgreSQL knowledge",
                    "text/plain",
                ),
            },
        )

    # The stored source remains available for future reprocessing.
    delete_upload_file.assert_not_called()

    assert len(created_documents) == 1
    document = created_documents[0]

    task_delay.assert_called_once_with(
        str(document.id),
        str(document.user_id),
    )

    set_document_status.assert_awaited_once()
    call = set_document_status.await_args

    assert call.kwargs["document"] is document
    assert call.kwargs["status"] == DocumentStatus.FAILED


def test_upload_deletes_stored_file_when_document_creation_fails(
    client: TestClient,
    monkeypatch,
):
    stored_path = Path("/tmp/fake-db-failed.txt")
    delete_upload_file = Mock()
    set_document_status = AsyncMock()
    task_delay = Mock()

    monkeypatch.setattr(
        "app.api.v1.documents.save_upload_file",
        lambda *, filename, data: stored_path,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.delete_upload_file",
        delete_upload_file,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.set_document_status",
        set_document_status,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

    async def fake_create_user_document(
        session,
        *,
        user,
        data,
        storage_key,
    ):
        assert storage_key == stored_path.name
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(
        "app.api.v1.documents.create_user_document",
        fake_create_user_document,
    )

    with pytest.raises(
        RuntimeError,
        match="Database unavailable",
    ):
        client.post(
            "/api/v1/documents/upload",
            headers=get_auth_headers(client),
            files={
                "file": (
                    "knowledge.txt",
                    b"PostgreSQL knowledge",
                    "text/plain",
                ),
            },
        )

    delete_upload_file.assert_called_once_with(stored_path)
    task_delay.assert_not_called()
    set_document_status.assert_not_awaited()
