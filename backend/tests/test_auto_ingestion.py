"""Tests for automatic background ingestion of text and file documents."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.document_status import DocumentStatus
from app.tasks.ingestion import _process_document_task


@pytest.fixture(autouse=True)
def mock_heartbeat(monkeypatch):
    async def fake_heartbeat(*args, **kwargs):
        pass

    monkeypatch.setattr(
        "app.tasks.ingestion.maintain_processing_heartbeat",
        fake_heartbeat,
    )


@pytest.mark.anyio
async def test_worker_processes_text_document_successfully(monkeypatch):
    """Test that text documents are directly chunked and embedded without storage_key."""
    doc_id = uuid4()
    user_id = uuid4()
    run_id = uuid4()
    content = "PostgreSQL is an advanced open-source database system."

    doc = SimpleNamespace(
        id=doc_id,
        user_id=user_id,
        source_type="text",
        content=content,
        title="PG Text Doc",
        source_name=None,
        storage_key=None,
        status=DocumentStatus.PENDING.value,
    )

    # Mock DB engine & session
    session = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()

    class FakeSessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(
        "app.tasks.ingestion.create_async_engine",
        lambda *args, **kwargs: engine,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.async_sessionmaker",
        lambda *args, **kwargs: FakeSessionContext,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.get_document_by_id_for_user",
        AsyncMock(return_value=doc),
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.claim_pending_file_processing",
        AsyncMock(return_value=run_id),
    )

    fake_chunks = [
        SimpleNamespace(
            chunk_index=0,
            content=content,
            char_start=0,
            char_end=len(content),
            embedding=[0.1] * 1536,
        )
    ]
    build_chunks = AsyncMock(return_value=fake_chunks)
    replace_chunks = AsyncMock()

    monkeypatch.setattr(
        "app.services.ingestion.build_embedded_document_chunks",
        build_chunks,
    )
    monkeypatch.setattr(
        "app.services.ingestion.replace_document_content_and_chunks",
        replace_chunks,
    )

    await _process_document_task(
        document_id=doc_id,
        user_id=user_id,
    )

    # Verified: chunks were built from document.content
    build_chunks.assert_awaited_once_with(
        document_id=doc_id,
        content=content,
    )
    replace_chunks.assert_awaited_once_with(
        session,
        document=doc,
        content=content,
        chunks=fake_chunks,
        processing_run_id=run_id,
    )


@pytest.mark.anyio
async def test_worker_records_error_message_when_text_empty(monkeypatch):
    """Test that empty text content records error_message and marks FAILED."""
    doc_id = uuid4()
    user_id = uuid4()
    run_id = uuid4()

    doc = SimpleNamespace(
        id=doc_id,
        user_id=user_id,
        source_type="text",
        content="   ",  # empty text
        title="Empty Doc",
        source_name=None,
        storage_key=None,
        status=DocumentStatus.PENDING.value,
    )

    session = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()

    class FakeSessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(
        "app.tasks.ingestion.create_async_engine",
        lambda *args, **kwargs: engine,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.async_sessionmaker",
        lambda *args, **kwargs: FakeSessionContext,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.get_document_by_id_for_user",
        AsyncMock(return_value=doc),
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.claim_pending_file_processing",
        AsyncMock(return_value=run_id),
    )

    mark_failed = AsyncMock()
    monkeypatch.setattr(
        "app.tasks.ingestion.mark_processing_run_failed",
        mark_failed,
    )

    with pytest.raises(ValueError, match="Document content is empty"):
        await _process_document_task(
            document_id=doc_id,
            user_id=user_id,
        )

    mark_failed.assert_awaited_once()
    assert "Document content is empty" in mark_failed.call_args.kwargs["error_message"]


@pytest.mark.anyio
async def test_worker_processes_markdown_file_successfully(monkeypatch):
    """Test that a Markdown file is read, extracted, chunked and marked READY."""
    doc_id = uuid4()
    user_id = uuid4()
    run_id = uuid4()
    md_content = "# System Architecture\n\n- Celery background queue\n- Redis broker"

    doc = SimpleNamespace(
        id=doc_id,
        user_id=user_id,
        source_type="file",
        content=None,
        title="architecture.md",
        source_name="architecture.md",
        storage_key="test-key.md",
        status=DocumentStatus.PENDING.value,
    )

    session = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()

    class FakeSessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(
        "app.tasks.ingestion.create_async_engine",
        lambda *args, **kwargs: engine,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.async_sessionmaker",
        lambda *args, **kwargs: FakeSessionContext,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.get_document_by_id_for_user",
        AsyncMock(return_value=doc),
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.claim_pending_file_processing",
        AsyncMock(return_value=run_id),
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.read_stored_file",
        lambda key: md_content.encode("utf-8"),
    )

    fake_chunks = [
        SimpleNamespace(
            chunk_index=0,
            content=md_content,
            char_start=0,
            char_end=len(md_content),
            embedding=[0.2] * 1536,
        )
    ]
    build_chunks = AsyncMock(return_value=fake_chunks)
    replace_chunks = AsyncMock()

    monkeypatch.setattr(
        "app.services.ingestion.build_embedded_document_chunks",
        build_chunks,
    )
    monkeypatch.setattr(
        "app.services.ingestion.replace_document_content_and_chunks",
        replace_chunks,
    )

    await _process_document_task(
        document_id=doc_id,
        user_id=user_id,
    )

    build_chunks.assert_awaited_once_with(
        document_id=doc_id,
        content=md_content,
    )
    replace_chunks.assert_awaited_once_with(
        session,
        document=doc,
        content=md_content,
        chunks=fake_chunks,
        processing_run_id=run_id,
    )


@pytest.mark.anyio
async def test_worker_records_error_when_pdf_has_no_text(monkeypatch):
    """Test that scanned/empty PDF without text records error message."""
    from io import BytesIO

    from pypdf import PdfWriter

    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    empty_pdf_bytes = output.getvalue()

    doc_id = uuid4()
    user_id = uuid4()
    run_id = uuid4()

    doc = SimpleNamespace(
        id=doc_id,
        user_id=user_id,
        source_type="file",
        content=None,
        title="scanned.pdf",
        source_name="scanned.pdf",
        storage_key="scanned.pdf",
        status=DocumentStatus.PENDING.value,
    )

    session = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()

    class FakeSessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(
        "app.tasks.ingestion.create_async_engine",
        lambda *args, **kwargs: engine,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.async_sessionmaker",
        lambda *args, **kwargs: FakeSessionContext,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.get_document_by_id_for_user",
        AsyncMock(return_value=doc),
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.claim_pending_file_processing",
        AsyncMock(return_value=run_id),
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.read_stored_file",
        lambda key: empty_pdf_bytes,
    )

    mark_failed = AsyncMock()
    monkeypatch.setattr(
        "app.services.ingestion.mark_processing_run_failed",
        mark_failed,
    )

    with pytest.raises(Exception, match="PDF file contains no extractable text"):
        await _process_document_task(
            document_id=doc_id,
            user_id=user_id,
        )

    mark_failed.assert_awaited_once()
    assert "PDF file contains no extractable text" in mark_failed.call_args.kwargs["error_message"]

