from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.document_status import DocumentStatus
from app.services.reprocessing import (
    EmptyDocumentContentError,
    UnsupportedDocumentReprocessingError,
    reprocess_text_document,
)


@pytest.mark.anyio
async def test_reprocess_text_document_marks_document_ready(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        source_type="text",
        content="PostgreSQL knowledge",
        status=DocumentStatus.READY.value,
    )
    session = AsyncMock()

    statuses: list[DocumentStatus] = []

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
        "app.services.reprocessing.set_document_status",
        fake_set_document_status,
    )
    monkeypatch.setattr(
        "app.services.reprocessing.chunk_document",
        fake_chunk_document,
    )
    monkeypatch.setattr(
        "app.services.reprocessing.embed_document_chunks",
        fake_embed_document_chunks,
    )

    result = await reprocess_text_document(
        session,
        document=document,
    )

    assert result is document
    assert statuses == [
        DocumentStatus.PROCESSING,
        DocumentStatus.READY,
    ]
    assert document.status == DocumentStatus.READY.value

    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_reprocess_rejects_file_document():
    document = SimpleNamespace(
        id=uuid4(),
        source_type="file",
        content="Extracted file content",
        status=DocumentStatus.READY.value,
    )
    session = AsyncMock()

    with pytest.raises(
        UnsupportedDocumentReprocessingError,
        match="Only text documents",
    ):
        await reprocess_text_document(
            session,
            document=document,
        )

    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_reprocess_rejects_empty_content():
    document = SimpleNamespace(
        id=uuid4(),
        source_type="text",
        content="   ",
        status=DocumentStatus.READY.value,
    )
    session = AsyncMock()

    with pytest.raises(
        EmptyDocumentContentError,
        match="Document content is empty",
    ):
        await reprocess_text_document(
            session,
            document=document,
        )

    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_reprocess_marks_document_failed(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        source_type="text",
        content="PostgreSQL knowledge",
        status=DocumentStatus.READY.value,
    )
    session = AsyncMock()

    statuses: list[DocumentStatus] = []

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
        "app.services.reprocessing.set_document_status",
        fake_set_document_status,
    )
    monkeypatch.setattr(
        "app.services.reprocessing.chunk_document",
        fake_chunk_document,
    )
    monkeypatch.setattr(
        "app.services.reprocessing.embed_document_chunks",
        fake_embed_document_chunks,
    )

    with pytest.raises(
        RuntimeError,
        match="Embedding failed",
    ):
        await reprocess_text_document(
            session,
            document=document,
        )

    session.rollback.assert_awaited_once()

    assert statuses == [
        DocumentStatus.PROCESSING,
        DocumentStatus.FAILED,
    ]
    assert document.status == DocumentStatus.FAILED.value