
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.document_status import DocumentStatus
from tests.test_document_upload import get_auth_headers


def make_file_document(
    *,
    document_status: DocumentStatus,
    storage_key: str | None = None,
):
    now = datetime.now(UTC)

    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        title="knowledge.pdf",
        source_type="file",
        source_name="knowledge.pdf",
        mime_type="application/pdf",
        storage_key=storage_key,
        content="Existing knowledge",
        status=document_status.value,
        created_at=now,
        updated_at=now,
    )


def mock_file_document(monkeypatch, document):
    async def fake_get_user_document(
        session,
        *,
        user,
        document_id,
    ):
        assert document_id == document.id
        document.user_id = user.id
        return document

    async def fake_set_document_status(
        session,
        *,
        document,
        status,
    ):
        document.status = status.value
        return document

    set_status = AsyncMock(
        side_effect=fake_set_document_status,
    )

    monkeypatch.setattr(
        "app.api.v1.documents.get_user_document",
        fake_get_user_document,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.set_document_status",
        set_status,
    )

    async def fake_claim(
        session,
        *,
        user,
        document_id,
    ):
        assert document_id == document.id
        assert user.id == document.user_id

        if document.status not in {
            DocumentStatus.READY.value,
            DocumentStatus.FAILED.value,
        }:
            return False

        document.status = DocumentStatus.PENDING.value
        return True

    claim = AsyncMock(
        side_effect=fake_claim,
    )

    monkeypatch.setattr(
        "app.api.v1.documents.claim_user_file_reprocessing",
        claim,
    )

    # Fake documents are not SQLAlchemy ORM instances.
    original_refresh = AsyncSession.refresh

    async def fake_refresh(
        self,
        instance,
        *args,
        **kwargs,
    ):
        if instance is document:
            return None

        return await original_refresh(
            self,
            instance,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        AsyncSession,
        "refresh",
        fake_refresh,
    )

    recover = AsyncMock(return_value=False)

    monkeypatch.setattr(
        "app.api.v1.documents.recover_user_stale_file_processing",
        recover,
    )

    return set_status, claim


@pytest.mark.parametrize(
    "initial_status",
    [
        DocumentStatus.READY,
        DocumentStatus.FAILED,
    ],
)
def test_file_reprocess_queues_background_job(
    client: TestClient,
    monkeypatch,
    initial_status,
):
    document = make_file_document(
        document_status=initial_status,
        storage_key=f"{uuid4()}.pdf",
    )

    set_status, claim = mock_file_document(
        monkeypatch,
        document,
    )

    task_delay = Mock()

    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

    response = client.post(
        f"/api/v1/documents/{document.id}/reprocess",
        headers=get_auth_headers(client),
    )

    assert response.status_code == 202

    body = response.json()

    assert body["id"] == str(document.id)
    assert body["status"] == DocumentStatus.PENDING.value

    # Internal storage key must never be exposed.
    assert "storage_key" not in body

    # Celery only receives document_id and user_id.
    task_delay.assert_called_once_with(
        str(document.id),
        str(document.user_id),
    )

    # Atomic claim replaces set_document_status(PENDING).
    claim.assert_awaited_once()
    set_status.assert_not_awaited()


def test_file_reprocess_rejects_missing_storage_key(
    client: TestClient,
    monkeypatch,
):
    document = make_file_document(
        document_status=DocumentStatus.READY,
        storage_key=None,
    )

    set_status, claim = mock_file_document(
        monkeypatch,
        document,
    )

    task_delay = Mock()

    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

    response = client.post(
        f"/api/v1/documents/{document.id}/reprocess",
        headers=get_auth_headers(client),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Document has no stored source file"
    )

    task_delay.assert_not_called()
    claim.assert_not_awaited()
    set_status.assert_not_awaited()


@pytest.mark.parametrize(
    "current_status",
    [
        DocumentStatus.PENDING,
        DocumentStatus.PROCESSING,
    ],
)
def test_file_reprocess_rejects_active_document(
    client: TestClient,
    monkeypatch,
    current_status,
):
    document = make_file_document(
        document_status=current_status,
        storage_key=f"{uuid4()}.pdf",
    )

    set_status, claim = mock_file_document(
        monkeypatch,
        document,
    )

    task_delay = Mock()

    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

    response = client.post(
        f"/api/v1/documents/{document.id}/reprocess",
        headers=get_auth_headers(client),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Document is already queued or processing"
    )

    task_delay.assert_not_called()
    claim.assert_not_awaited()
    set_status.assert_not_awaited()


def test_file_reprocess_returns_503_when_broker_fails(
    client: TestClient,
    monkeypatch,
):
    document = make_file_document(
        document_status=DocumentStatus.READY,
        storage_key=f"{uuid4()}.pdf",
    )

    set_status, claim = mock_file_document(
        monkeypatch,
        document,
    )

    task_delay = Mock(
        side_effect=RuntimeError("Broker unavailable"),
    )

    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

    response = client.post(
        f"/api/v1/documents/{document.id}/reprocess",
        headers=get_auth_headers(client),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Unable to schedule document reprocessing"
    )

    task_delay.assert_called_once_with(
        str(document.id),
        str(document.user_id),
    )

    claim.assert_awaited_once()
    set_status.assert_awaited_once()

    assert (
        set_status.await_args.kwargs["status"]
        == DocumentStatus.FAILED
    )

    assert document.status == DocumentStatus.FAILED.value

    # Existing extracted content must remain untouched.
    assert document.content == "Existing knowledge"


def test_file_reprocess_rejects_when_atomic_claim_lost(
    client: TestClient,
    monkeypatch,
):
    document = make_file_document(
        document_status=DocumentStatus.READY,
        storage_key=f"{uuid4()}.pdf",
    )

    set_status, _ = mock_file_document(
        monkeypatch,
        document,
    )

    # Simulate another request claiming the document first.
    claim = AsyncMock(return_value=False)
    task_delay = Mock()

    monkeypatch.setattr(
        "app.api.v1.documents.claim_user_file_reprocessing",
        claim,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

    response = client.post(
        f"/api/v1/documents/{document.id}/reprocess",
        headers=get_auth_headers(client),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Document is already queued or processing"
    )

    claim.assert_awaited_once()
    task_delay.assert_not_called()
    set_status.assert_not_awaited()

    # The losing request must not change existing data.
    assert document.status == DocumentStatus.READY.value
    assert document.content == "Existing knowledge"


def test_file_reprocess_recovers_stale_processing_lease(
    client: TestClient,
    monkeypatch,
):
    document = make_file_document(
        document_status=DocumentStatus.PROCESSING,
        storage_key=f"{uuid4()}.pdf",
    )

    set_status, claim = mock_file_document(
        monkeypatch,
        document,
    )

    async def fake_recover(
        session,
        *,
        user,
        document_id,
    ):
        assert document_id == document.id
        assert user.id == document.user_id

        # Simulate the conditional UPDATE expiring the lease.
        document.status = DocumentStatus.FAILED.value
        return True

    recover = AsyncMock(side_effect=fake_recover)
    task_delay = Mock()

    monkeypatch.setattr(
        "app.api.v1.documents.recover_user_stale_file_processing",
        recover,
    )
    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

    response = client.post(
        f"/api/v1/documents/{document.id}/reprocess",
        headers=get_auth_headers(client),
    )

    assert response.status_code == 202

    body = response.json()

    assert body["id"] == str(document.id)
    assert body["status"] == DocumentStatus.PENDING.value

    recover.assert_awaited_once()
    claim.assert_awaited_once()

    task_delay.assert_called_once_with(
        str(document.id),
        str(document.user_id),
    )

    # Atomic Claim performs the PENDING transition.
    # The API must not update status independently.
    set_status.assert_not_awaited()

    assert document.content == "Existing knowledge"
