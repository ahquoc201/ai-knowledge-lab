
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.document_status import DocumentStatus
from app.services.document import (
    DocumentProcessingError,
    delete_user_document,
)
from app.services.file_storage import save_upload_file
from tests.test_document_upload import get_auth_headers


def configure_test_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: SimpleNamespace(
            upload_storage_dir=tmp_path,
        ),
    )


def test_delete_document_removes_original_file(
    client: TestClient,
    monkeypatch,
    tmp_path,
):
    configure_test_storage(monkeypatch, tmp_path)

    task_delay = Mock()

    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

    owner_headers = get_auth_headers(client)
    another_user_headers = get_auth_headers(client)

    upload_response = client.post(
        "/api/v1/documents/upload",
        headers=owner_headers,
        files={
            "file": (
                "knowledge.txt",
                b"Persistent knowledge",
                "text/plain",
            ),
        },
    )

    assert upload_response.status_code == 201

    body = upload_response.json()
    document_id = body["id"]

    stored_files = list(tmp_path.iterdir())

    assert len(stored_files) == 1

    stored_path = stored_files[0]

    assert stored_path.read_bytes() == b"Persistent knowledge"

    task_delay.assert_called_once_with(
        document_id,
        body["user_id"],
    )

    # Another user must not delete the document.
    unauthorized_response = client.delete(
        f"/api/v1/documents/{document_id}",
        headers=another_user_headers,
    )

    assert unauthorized_response.status_code == 404
    assert stored_path.exists()

    # Owner deletes the document.
    delete_response = client.delete(
        f"/api/v1/documents/{document_id}",
        headers=owner_headers,
    )

    assert delete_response.status_code == 204

    # Source file is deleted after DB deletion.
    assert not stored_path.exists()

    get_response = client.get(
        f"/api/v1/documents/{document_id}",
        headers=owner_headers,
    )

    assert get_response.status_code == 404


@pytest.mark.anyio
async def test_database_delete_failure_preserves_source_file(
    monkeypatch,
    tmp_path,
):
    configure_test_storage(monkeypatch, tmp_path)

    stored_path = save_upload_file(
        filename="knowledge.txt",
        data=b"Original knowledge",
    )

    document = SimpleNamespace(
        id=uuid4(),
        storage_key=stored_path.name,
        status=DocumentStatus.READY.value,
    )

    user = SimpleNamespace(id=uuid4())
    session = AsyncMock()

    get_document = AsyncMock(return_value=document)
    delete_document = AsyncMock(
        side_effect=RuntimeError("Database delete failed")
    )

    monkeypatch.setattr(
        "app.services.document.get_document_by_id_for_user_for_update",
        get_document,
    )
    monkeypatch.setattr(
        "app.services.document.delete_document",
        delete_document,
    )

    with pytest.raises(
        RuntimeError,
        match="Database delete failed",
    ):
        await delete_user_document(
            session,
            user=user,
            document_id=document.id,
        )

    assert stored_path.exists()
    assert stored_path.read_bytes() == b"Original knowledge"

    get_document.assert_awaited_once_with(
        session,
        document_id=document.id,
        user_id=user.id,
    )

    delete_document.assert_awaited_once_with(
        session,
        document=document,
    )


@pytest.mark.anyio
async def test_file_cleanup_failure_does_not_mask_db_success(
    monkeypatch,
    tmp_path,
    caplog,
):
    configure_test_storage(monkeypatch, tmp_path)

    stored_path = save_upload_file(
        filename="knowledge.txt",
        data=b"Persistent knowledge",
    )

    document = SimpleNamespace(
        id=uuid4(),
        storage_key=stored_path.name,
        status=DocumentStatus.READY.value,
    )

    user = SimpleNamespace(id=uuid4())
    session = AsyncMock()

    get_document = AsyncMock(return_value=document)

    operations = []

    async def fake_delete_document(
        session,
        *,
        document,
    ):
        assert stored_path.exists()
        operations.append("database")

    delete_document = AsyncMock(
        side_effect=fake_delete_document,
    )

    def fake_delete_file(storage_key):
        assert storage_key == stored_path.name
        operations.append("filesystem")
        raise PermissionError("Storage is read-only")

    delete_file = Mock(side_effect=fake_delete_file)

    monkeypatch.setattr(
        "app.services.document.get_document_by_id_for_user_for_update",
        get_document,
    )
    monkeypatch.setattr(
        "app.services.document.delete_document",
        delete_document,
    )
    monkeypatch.setattr(
        "app.services.document.delete_stored_file",
        delete_file,
    )

    result = await delete_user_document(
        session,
        user=user,
        document_id=document.id,
    )

    assert result is True

    assert operations == [
        "database",
        "filesystem",
    ]

    delete_document.assert_awaited_once_with(
        session,
        document=document,
    )

    delete_file.assert_called_once_with(
        stored_path.name,
    )

    assert "Failed to clean up source file" in caplog.text
    assert stored_path.exists()


@pytest.mark.anyio
async def test_processing_document_cannot_be_deleted(
    monkeypatch,
    tmp_path,
):
    configure_test_storage(monkeypatch, tmp_path)

    stored_path = save_upload_file(
        filename="knowledge.txt",
        data=b"Knowledge being processed",
    )

    document = SimpleNamespace(
        id=uuid4(),
        storage_key=stored_path.name,
        status=DocumentStatus.PROCESSING.value,
        processing_started_at=datetime.now(UTC),
        processing_heartbeat_at=datetime.now(UTC),
    )

    user = SimpleNamespace(id=uuid4())
    session = AsyncMock()
    session.scalar.return_value = (
        datetime.now(UTC) - timedelta(minutes=5)
    )

    get_document = AsyncMock(return_value=document)
    delete_document = AsyncMock()
    delete_file = Mock()

    monkeypatch.setattr(
        "app.services.document.get_document_by_id_for_user_for_update",
        get_document,
    )
    monkeypatch.setattr(
        "app.services.document.delete_document",
        delete_document,
    )
    monkeypatch.setattr(
        "app.services.document.delete_stored_file",
        delete_file,
    )

    with pytest.raises(
        DocumentProcessingError,
        match="Document is currently processing",
    ):
        await delete_user_document(
            session,
            user=user,
            document_id=document.id,
        )

    # Rollback releases the PostgreSQL row lock.
    session.rollback.assert_awaited_once()

    # Neither DB record nor original file is deleted.
    delete_document.assert_not_awaited()
    delete_file.assert_not_called()

    assert stored_path.exists()
    assert stored_path.read_bytes() == b"Knowledge being processed"


def test_delete_processing_document_returns_409(
    client: TestClient,
    monkeypatch,
):
    document_id = uuid4()

    async def fake_delete_user_document(
        session,
        *,
        user,
        document_id,
    ):
        raise DocumentProcessingError(
            "Document is currently processing"
        )

    monkeypatch.setattr(
        "app.api.v1.documents.delete_user_document",
        fake_delete_user_document,
    )

    response = client.delete(
        f"/api/v1/documents/{document_id}",
        headers=get_auth_headers(client),
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Document is currently processing",
    }
