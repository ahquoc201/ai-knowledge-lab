
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.document_status import DocumentStatus
from app.services.ingestion import ingest_file, process_document


@pytest.mark.anyio
async def test_process_document_marks_document_ready(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        title="knowledge.txt",
        source_name="knowledge.txt",
        content=None,
        status=DocumentStatus.PENDING.value,
    )
    session = AsyncMock()

    statuses: list[DocumentStatus] = []

    async def fake_set_document_status(
        session,
        *,
        document,
        status,
        error_message=None,
    ):
        statuses.append(status)
        document.status = status.value
        return document

    extract_text = Mock(
        return_value="PostgreSQL knowledge",
    )

    chunks = [
        SimpleNamespace(
            document_id=document.id,
            chunk_index=0,
            content="PostgreSQL knowledge",
            embedding=[0.1, 0.2, 0.3],
        ),
    ]

    build_chunks = AsyncMock(
        return_value=chunks,
    )

    async def fake_replace_document_data(
        session,
        *,
        document,
        content,
        chunks,
        processing_run_id,
    ):
        document.content = content
        document.status = DocumentStatus.READY.value
        return chunks

    replace_data = AsyncMock(
        side_effect=fake_replace_document_data,
    )

    monkeypatch.setattr(
        "app.services.ingestion.set_document_status",
        fake_set_document_status,
    )
    monkeypatch.setattr(
        "app.services.ingestion.extract_text",
        extract_text,
    )
    monkeypatch.setattr(
        "app.services.ingestion.build_embedded_document_chunks",
        build_chunks,
    )
    monkeypatch.setattr(
        "app.services.ingestion.replace_document_content_and_chunks",
        replace_data,
    )

    result = await process_document(
        session,
        document=document,
        data=b"PostgreSQL knowledge",
    )

    assert result is document

    extract_text.assert_called_once_with(
        filename="knowledge.txt",
        data=b"PostgreSQL knowledge",
    )

    build_chunks.assert_awaited_once_with(
        document_id=document.id,
        content="PostgreSQL knowledge",
    )

    replace_data.assert_awaited_once_with(
        session,
        document=document,
        content="PostgreSQL knowledge",
        chunks=chunks,
        processing_run_id=None,
    )

    assert statuses == [
        DocumentStatus.PROCESSING,
    ]

    assert document.status == DocumentStatus.READY.value
    assert document.content == "PostgreSQL knowledge"

    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_process_document_marks_document_failed(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        title="knowledge.txt",
        source_name="knowledge.txt",
        content="Existing knowledge",
        status=DocumentStatus.PENDING.value,
    )
    session = AsyncMock()

    statuses: list[DocumentStatus] = []

    async def fake_set_document_status(
        session,
        *,
        document,
        status,
        error_message=None,
    ):
        statuses.append(status)
        document.status = status.value
        document.error_message = error_message
        return document

    extract_text = Mock(
        return_value="PostgreSQL knowledge",
    )

    build_chunks = AsyncMock(
        side_effect=RuntimeError("Embedding failed"),
    )

    replace_data = AsyncMock()

    monkeypatch.setattr(
        "app.services.ingestion.set_document_status",
        fake_set_document_status,
    )
    monkeypatch.setattr(
        "app.services.ingestion.extract_text",
        extract_text,
    )
    monkeypatch.setattr(
        "app.services.ingestion.build_embedded_document_chunks",
        build_chunks,
    )
    monkeypatch.setattr(
        "app.services.ingestion.replace_document_content_and_chunks",
        replace_data,
    )

    with pytest.raises(
        RuntimeError,
        match="Embedding failed",
    ):
        await process_document(
            session,
            document=document,
            data=b"PostgreSQL knowledge",
        )

    build_chunks.assert_awaited_once_with(
        document_id=document.id,
        content="PostgreSQL knowledge",
    )

    # Embedding failed before the database replacement.
    replace_data.assert_not_awaited()

    session.rollback.assert_awaited_once()

    assert statuses == [
        DocumentStatus.PROCESSING,
        DocumentStatus.FAILED,
    ]

    assert document.status == DocumentStatus.FAILED.value
    assert document.error_message == "Embedding failed"

    # Existing content must not be overwritten.
    assert document.content == "Existing knowledge"


@pytest.mark.anyio
async def test_ingest_file_creates_pending_document_then_processes_it(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        status=DocumentStatus.PENDING.value,
    )
    user = SimpleNamespace(id=uuid4())
    session = AsyncMock()

    async def fake_create_user_document(
        session,
        *,
        user,
        data,
    ):
        assert data.title == "knowledge.txt"
        assert data.content is None
        assert data.source_type == "file"
        assert data.source_name == "knowledge.txt"
        assert data.mime_type == "text/plain"

        return document

    async def fake_process_document(
        session,
        *,
        document,
        data,
    ):
        assert data == b"PostgreSQL knowledge"
        return document

    create_document = AsyncMock(
        side_effect=fake_create_user_document,
    )
    process = AsyncMock(
        side_effect=fake_process_document,
    )

    monkeypatch.setattr(
        "app.services.ingestion.create_user_document",
        create_document,
    )
    monkeypatch.setattr(
        "app.services.ingestion.process_document",
        process,
    )

    result = await ingest_file(
        session,
        user=user,
        filename="knowledge.txt",
        data=b"PostgreSQL knowledge",
        mime_type="text/plain",
    )

    assert result is document

    assert create_document.await_count == 1

    process.assert_awaited_once_with(
        session,
        document=document,
        data=b"PostgreSQL knowledge",
    )
