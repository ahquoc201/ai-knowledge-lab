import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.document_status import DocumentStatus
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk import (
    DocumentChunkWriteConflictError,
    list_document_chunks,
    replace_document_chunks,
    save_chunk_embeddings,
)
from tests.test_documents import register_and_login


def create_test_document(
    client: TestClient,
) -> tuple[UUID, dict[str, str]]:
    token = register_and_login(
        client,
        email=f"chunk-concurrency-{uuid4()}@example.com",
        password="TestPassword123!",
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Concurrency test",
            "content": "abcdefghij",
            "source_type": "text",
        },
    )

    assert response.status_code == 201, response.text

    return UUID(response.json()["id"]), headers


async def set_document_state(
    document_id: UUID,
    *,
    source_type: str,
    status: DocumentStatus,
) -> None:
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )

    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with factory() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    source_type=source_type,
                    status=status.value,
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


def test_file_pending_and_processing_reject_manual_writes(
    client: TestClient,
):
    document_id, headers = create_test_document(client)

    try:
        for current_status in (
            DocumentStatus.PENDING,
            DocumentStatus.PROCESSING,
        ):
            asyncio.run(
                set_document_state(
                    document_id,
                    source_type="file",
                    status=current_status,
                )
            )

            chunk_response = client.post(
                f"/api/v1/documents/{document_id}/chunks",
                headers=headers,
                json={
                    "chunk_size": 4,
                    "overlap": 1,
                },
            )

            assert chunk_response.status_code == 409, (
                chunk_response.text
            )

            # There are no chunks. This path must still return 409.
            embedding_response = client.post(
                f"/api/v1/documents/{document_id}/embeddings",
                headers=headers,
            )

            assert embedding_response.status_code == 409, (
                embedding_response.text
            )

    finally:
        # Restore the document before using the ordinary DELETE API.
        asyncio.run(
            set_document_state(
                document_id,
                source_type="text",
                status=DocumentStatus.READY,
            )
        )

        delete_response = client.delete(
            f"/api/v1/documents/{document_id}",
            headers=headers,
        )

        assert delete_response.status_code == 204


async def run_stale_embedding_checks(
    document_id: UUID,
) -> None:
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )

    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        # Session A reads chunks and begins embedding computation.
        async with factory() as embedding_session:
            old_chunks = await list_document_chunks(
                embedding_session,
                document_id=document_id,
            )

            assert old_chunks

            old_chunk_ids = {chunk.id for chunk in old_chunks}

            # Simulate embeddings computed from the old snapshot.
            embeddings = [
                [0.1] * 384
                for _ in old_chunks
            ]

            # Session B replaces the chunks before A saves.
            async with factory() as rewrite_session:
                new_chunks = [
                    DocumentChunk(
                        document_id=document_id,
                        chunk_index=0,
                        content="replacement",
                        char_start=0,
                        char_end=11,
                    ),
                ]

                await replace_document_chunks(
                    rewrite_session,
                    document_id=document_id,
                    chunks=new_chunks,
                )

            # Session A must reject stale embeddings.
            with pytest.raises(
                DocumentChunkWriteConflictError,
                match="changed during embedding",
            ):
                await save_chunk_embeddings(
                    embedding_session,
                    chunks=old_chunks,
                    embeddings=embeddings,
                )

            await embedding_session.rollback()

        # Verify the replacement is still intact.
        async with factory() as verify_session:
            current_chunks = await list_document_chunks(
                verify_session,
                document_id=document_id,
            )

            assert len(current_chunks) == 1
            assert current_chunks[0].content == "replacement"
            assert current_chunks[0].id not in old_chunk_ids
            assert current_chunks[0].embedding is None

    finally:
        await engine.dispose()


def test_stale_embeddings_cannot_overwrite_replaced_chunks(
    client: TestClient,
):
    document_id, headers = create_test_document(client)

    try:
        # Create the initial chunk snapshot through the real API.
        response = client.post(
            f"/api/v1/documents/{document_id}/chunks",
            headers=headers,
            json={
                "chunk_size": 4,
                "overlap": 1,
            },
        )

        assert response.status_code == 200, response.text
        assert len(response.json()) == 3

        asyncio.run(
            run_stale_embedding_checks(document_id)
        )

    finally:
        delete_response = client.delete(
            f"/api/v1/documents/{document_id}",
            headers=headers,
        )

        assert delete_response.status_code == 204
