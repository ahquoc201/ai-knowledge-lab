import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.document_status import DocumentStatus
from app.models.document import Document
from app.repositories.document import (
    mark_processing_run_failed,
    recover_stale_file_processing,
)
from app.repositories.document_chunk import (
    ProcessingLeaseLostError,
    replace_document_content_and_chunks,
)
from tests.test_document_upload import get_auth_headers


async def verify_processing_lease_recovery(
    *,
    document_id: UUID,
    user_id: UUID,
) -> None:
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    processing_run_id = uuid4()
    now = datetime.now(UTC)

    try:
        # Simulate a currently running worker.
        async with session_factory() as session:
            await session.execute(
                update(Document)
                .where(
                    Document.id == document_id,
                    Document.user_id == user_id,
                )
                .values(
                    source_type="file",
                    storage_key=f"{uuid4()}.txt",
                    status=DocumentStatus.PROCESSING.value,
                    processing_run_id=processing_run_id,
                    processing_started_at=now - timedelta(minutes=2),
                    processing_heartbeat_at=now,
                )
            )
            await session.commit()

        # A fresh heartbeat must not be recovered.
        async with session_factory() as session:
            recovered = await recover_stale_file_processing(
                session,
                document_id=document_id,
                user_id=user_id,
            )

            assert recovered is False

        # Simulate a worker whose heartbeat stopped
        # more than five minutes ago.
        async with session_factory() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    processing_heartbeat_at=(
                        now - timedelta(minutes=10)
                    ),
                )
            )
            await session.commit()

        # Recovery must respect document ownership.
        async with session_factory() as session:
            unauthorized = await recover_stale_file_processing(
                session,
                document_id=document_id,
                user_id=uuid4(),
            )

            assert unauthorized is False

        # Two independent sessions compete for recovery.
        async def attempt_recovery() -> bool:
            async with session_factory() as session:
                return await recover_stale_file_processing(
                    session,
                    document_id=document_id,
                    user_id=user_id,
                )

        results = await asyncio.wait_for(
            asyncio.gather(
                attempt_recovery(),
                attempt_recovery(),
            ),
            timeout=15,
        )

        assert results.count(True) == 1
        assert results.count(False) == 1

        # Check persisted state after recovery.
        async with session_factory() as session:
            document = await session.scalar(
                select(Document).where(
                    Document.id == document_id
                )
            )

            assert document is not None
            assert document.status == DocumentStatus.FAILED.value
            assert document.processing_run_id is None
            assert document.processing_started_at is None
            assert document.processing_heartbeat_at is None

            # Previously extracted data must be preserved.
            assert document.content == "Original knowledge"

        # The old worker must not be able to mark
        # the recovered document as FAILED again.
        async with session_factory() as session:
            marked = await mark_processing_run_failed(
                session,
                document_id=document_id,
                user_id=user_id,
                processing_run_id=processing_run_id,
            )

            assert marked is False

        # The old worker must not replace stored data.
        async with session_factory() as session:
            document = await session.get(
                Document,
                document_id,
            )

            assert document is not None

            try:
                await replace_document_content_and_chunks(
                    session,
                    document=document,
                    content="Stale worker content",
                    chunks=[],
                    processing_run_id=processing_run_id,
                )

            except ProcessingLeaseLostError:
                await session.rollback()

            else:
                raise AssertionError(
                    "Stale worker was allowed to commit"
                )

            await session.refresh(document)

            assert document.content == "Original knowledge"

    finally:
        # Release the test document even if an assertion fails.
        try:
            async with session_factory() as session:
                await session.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(
                        status=DocumentStatus.FAILED.value,
                        processing_run_id=None,
                        processing_started_at=None,
                        processing_heartbeat_at=None,
                    )
                )
                await session.commit()
        finally:
            await engine.dispose()


def test_processing_lease_recovery_with_postgres(
    client: TestClient,
):
    headers = get_auth_headers(client)

    response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Processing lease recovery test",
            "content": "Original knowledge",
            "source_type": "text",
        },
    )

    assert response.status_code == 201, response.text

    document = response.json()
    document_id = UUID(document["id"])
    user_id = UUID(document["user_id"])

    try:
        asyncio.run(
            verify_processing_lease_recovery(
                document_id=document_id,
                user_id=user_id,
            )
        )
    finally:
        delete_response = client.delete(
            f"/api/v1/documents/{document_id}",
            headers=headers,
        )

        assert delete_response.status_code == 204
