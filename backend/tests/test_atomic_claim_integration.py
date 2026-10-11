
import asyncio
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
    claim_file_document_reprocessing,
)
from tests.test_documents import register_and_login


async def run_atomic_claim_checks(
    *,
    document_id: UUID,
    owner_id: UUID,
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

    try:
        # Prepare an existing file document in READY state.
        async with session_factory() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status=DocumentStatus.READY.value,
                    source_type="file",
                    source_name="knowledge.pdf",
                    mime_type="application/pdf",
                    storage_key=f"{uuid4()}.pdf",
                )
            )
            await session.commit()

        # Both sessions wait for the same start signal.
        start_event = asyncio.Event()

        async def attempt_claim() -> bool:
            async with session_factory() as session:
                await start_event.wait()

                return await claim_file_document_reprocessing(
                    session,
                    document_id=document_id,
                    user_id=owner_id,
                )

        task_a = asyncio.create_task(attempt_claim())
        task_b = asyncio.create_task(attempt_claim())

        start_event.set()

        results = await asyncio.wait_for(
            asyncio.gather(task_a, task_b),
            timeout=15,
        )

        # Exactly one session wins the atomic UPDATE.
        assert results.count(True) == 1
        assert results.count(False) == 1

        async with session_factory() as session:
            current_status = await session.scalar(
                select(Document.status).where(
                    Document.id == document_id
                )
            )

        assert current_status == DocumentStatus.PENDING.value

        # Reset to FAILED to test ownership and retry.
        async with session_factory() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=DocumentStatus.FAILED.value)
            )
            await session.commit()

        # Another user must not be able to claim it.
        async with session_factory() as session:
            unauthorized = await claim_file_document_reprocessing(
                session,
                document_id=document_id,
                user_id=uuid4(),
            )

        assert unauthorized is False

        # The owner can retry a FAILED file document.
        async with session_factory() as session:
            retry_claim = await claim_file_document_reprocessing(
                session,
                document_id=document_id,
                user_id=owner_id,
            )

        assert retry_claim is True

        # Reset to READY, but remove the stored source key.
        async with session_factory() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status=DocumentStatus.READY.value,
                    storage_key=None,
                )
            )
            await session.commit()

        # Documents without a stored source cannot be claimed.
        async with session_factory() as session:
            missing_source_claim = (
                await claim_file_document_reprocessing(
                    session,
                    document_id=document_id,
                    user_id=owner_id,
                )
            )

        assert missing_source_claim is False

    finally:
        await engine.dispose()


def test_atomic_claim_with_concurrent_postgres_sessions(
    client: TestClient,
):
    token = register_and_login(
        client,
        email=f"atomic-claim-{uuid4()}@example.com",
        password="TestPassword123!",
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    # Create a document through the actual API.
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Atomic claim integration test",
            "content": "Knowledge for concurrency testing.",
            "source_type": "text",
        },
    )

    assert response.status_code == 201, response.text

    body = response.json()

    document_id = UUID(body["id"])
    owner_id = UUID(body["user_id"])

    try:
        asyncio.run(
            run_atomic_claim_checks(
                document_id=document_id,
                owner_id=owner_id,
            )
        )
    finally:
        # Clean up the test document.
        delete_response = client.delete(
            f"/api/v1/documents/{document_id}",
            headers=headers,
        )

        assert delete_response.status_code == 204
