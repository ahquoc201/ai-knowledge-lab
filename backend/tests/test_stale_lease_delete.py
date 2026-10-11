
import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.document_status import DocumentStatus
from app.models.document import Document
from tests.test_document_upload import get_auth_headers


async def set_processing_lease(
    document_id: UUID,
    *,
    heartbeat_at: datetime,
) -> None:
    """Set a processing lease using a real PostgreSQL session."""
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )

    try:
        async with AsyncSession(engine) as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status=DocumentStatus.PROCESSING.value,
                    processing_run_id=uuid4(),
                    processing_started_at=(
                        heartbeat_at - timedelta(minutes=1)
                    ),
                    processing_heartbeat_at=heartbeat_at,
                )
            )

            await session.commit()
    finally:
        await engine.dispose()


def test_delete_respects_processing_lease_expiration(
    client: TestClient,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: SimpleNamespace(
            upload_storage_dir=tmp_path,
        ),
    )

    task_delay = Mock()

    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task",
        SimpleNamespace(delay=task_delay),
    )

    headers = get_auth_headers(client)

    upload_response = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={
            "file": (
                "knowledge.txt",
                b"Persistent knowledge",
                "text/plain",
            ),
        },
    )

    assert upload_response.status_code == 201

    document_id = UUID(upload_response.json()["id"])

    stored_files = list(tmp_path.iterdir())
    assert len(stored_files) == 1

    stored_path = stored_files[0]
    deleted = False

    try:
        # Case 1: heartbeat is still fresh.
        asyncio.run(
            set_processing_lease(
                document_id,
                heartbeat_at=datetime.now(UTC),
            )
        )

        active_response = client.delete(
            f"/api/v1/documents/{document_id}",
            headers=headers,
        )

        assert active_response.status_code == 409
        assert active_response.json()["detail"] == (
            "Document is currently processing"
        )

        # The original file must survive.
        assert stored_path.exists()

        get_response = client.get(
            f"/api/v1/documents/{document_id}",
            headers=headers,
        )

        assert get_response.status_code == 200

        # Case 2: simulate heartbeat expired 10 minutes ago.
        asyncio.run(
            set_processing_lease(
                document_id,
                heartbeat_at=(
                    datetime.now(UTC)
                    - timedelta(minutes=10)
                ),
            )
        )

        stale_response = client.delete(
            f"/api/v1/documents/{document_id}",
            headers=headers,
        )

        assert stale_response.status_code == 204
        deleted = True

        # The original file must now be deleted.
        assert not stored_path.exists()

        get_response = client.get(
            f"/api/v1/documents/{document_id}",
            headers=headers,
        )

        assert get_response.status_code == 404

    finally:
        # Clean up the test document if an assertion failed.
        if not deleted:
            asyncio.run(
                set_processing_lease(
                    document_id,
                    heartbeat_at=(
                        datetime.now(UTC)
                        - timedelta(minutes=10)
                    ),
                )
            )

            client.delete(
                f"/api/v1/documents/{document_id}",
                headers=headers,
            )
