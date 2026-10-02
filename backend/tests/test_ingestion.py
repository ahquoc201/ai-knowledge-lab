from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.document_status import DocumentStatus
from app.services.ingestion import ingest_file


@pytest.mark.anyio
async def test_ingest_file_marks_document_ready(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        status=DocumentStatus.PENDING.value,
    )
    user = SimpleNamespace(id=uuid4())
    session = AsyncMock()

    statuses: list[DocumentStatus] = []

    async def fake_create_user_document(
        session,
        *,
        user,
        data,
    ):
        assert data.content == "PostgreSQL knowledge"
        assert data.source_type == "file"
        assert data.source_name == "knowledge.txt"
        return document

    async def fake_set_document_status(
        session,
        *,
        document,
        status,
    ):
        statuses.append(status)
        document.status = status.value
        return document

    async def fake_chunk_document(
        session,
        *,
        document,
    ):
        return []

    async def fake_embed_document_chunks(
        session,
        *,
        document_id,
    ):
        assert document_id == document.id
        return []

    monkeypatch.setattr(
        "app.services.ingestion.create_user_document",
        fake_create_user_document,
    )
    monkeypatch.setattr(
        "app.services.ingestion.set_document_status",
        fake_set_document_status,
    )
    monkeypatch.setattr(
        "app.services.ingestion.chunk_document",
        fake_chunk_document,
    )
    monkeypatch.setattr(
        "app.services.ingestion.embed_document_chunks",
        fake_embed_document_chunks,
    )

    result = await ingest_file(
        session,
        user=user,
        filename="knowledge.txt",
        data=b"PostgreSQL knowledge",
        mime_type="text/plain",
    )

    assert result is document
    assert statuses == [
        DocumentStatus.PROCESSING,
        DocumentStatus.READY,
    ]
    assert document.status == DocumentStatus.READY.value

    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_ingest_file_marks_document_failed(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        status=DocumentStatus.PENDING.value,
    )
    user = SimpleNamespace(id=uuid4())
    session = AsyncMock()

    statuses: list[DocumentStatus] = []

    async def fake_create_user_document(
        session,
        *,
        user,
        data,
    ):
        return document

    async def fake_set_document_status(
        session,
        *,
        document,
        status,
    ):
        statuses.append(status)
        document.status = status.value
        return document

    async def fake_chunk_document(
        session,
        *,
        document,
    ):
        return []

    async def fake_embed_document_chunks(
        session,
        *,
        document_id,
    ):
        raise RuntimeError("Embedding failed")

    monkeypatch.setattr(
        "app.services.ingestion.create_user_document",
        fake_create_user_document,
    )
    monkeypatch.setattr(
        "app.services.ingestion.set_document_status",
        fake_set_document_status,
    )
    monkeypatch.setattr(
        "app.services.ingestion.chunk_document",
        fake_chunk_document,
    )
    monkeypatch.setattr(
        "app.services.ingestion.embed_document_chunks",
        fake_embed_document_chunks,
    )

    with pytest.raises(
        RuntimeError,
        match="Embedding failed",
    ):
        await ingest_file(
            session,
            user=user,
            filename="knowledge.txt",
            data=b"PostgreSQL knowledge",
            mime_type="text/plain",
        )

    session.rollback.assert_awaited_once()

    assert statuses == [
        DocumentStatus.PROCESSING,
        DocumentStatus.FAILED,
    ]
    assert document.status == DocumentStatus.FAILED.value