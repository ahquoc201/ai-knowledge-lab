
from types import SimpleNamespace
from unittest.mock import AsyncMock, call
from uuid import uuid4

import pytest

from app.core.document_status import DocumentStatus
from app.services.reprocessing import (
    EmptyDocumentContentError,
    UnsupportedDocumentReprocessingError,
    reprocess_text_document,
)


def make_text_document(
    content: str = "PostgreSQL knowledge",
):
    return SimpleNamespace(
        id=uuid4(),
        source_type="text",
        content=content,
        status=DocumentStatus.READY.value,
    )


def mock_document_status(monkeypatch):
    async def fake_set_document_status(
        session,
        *,
        document,
        status,
        error_message=None,
    ):
        document.status = status.value
        document.error_message = error_message
        return document

    set_status = AsyncMock(
        side_effect=fake_set_document_status,
    )

    monkeypatch.setattr(
        "app.services.reprocessing.set_document_status",
        set_status,
    )

    return set_status


@pytest.mark.anyio
async def test_reprocess_text_document_marks_document_ready(
    monkeypatch,
):
    document = make_text_document()
    session = AsyncMock()

    set_status = mock_document_status(monkeypatch)

    chunks = [
        SimpleNamespace(
            document_id=document.id,
            chunk_index=0,
            content="PostgreSQL knowledge",
            embedding=[0.1, 0.2, 0.3],
        ),
    ]

    build_chunks = AsyncMock(return_value=chunks)

    async def fake_replace(
        session,
        *,
        document,
        content,
        chunks,
    ):
        document.content = content
        document.status = DocumentStatus.READY.value
        return chunks

    replace_data = AsyncMock(side_effect=fake_replace)

    monkeypatch.setattr(
        "app.services.reprocessing.build_embedded_document_chunks",
        build_chunks,
    )
    monkeypatch.setattr(
        "app.services.reprocessing.replace_document_content_and_chunks",
        replace_data,
    )

    result = await reprocess_text_document(
        session,
        document=document,
    )

    assert result is document
    assert document.status == DocumentStatus.READY.value
    assert document.content == "PostgreSQL knowledge"

    set_status.assert_awaited_once_with(
        session,
        document=document,
        status=DocumentStatus.PROCESSING,
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
    )

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
    session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_reprocess_rejects_empty_content():
    document = make_text_document(content="   ")
    session = AsyncMock()

    with pytest.raises(
        EmptyDocumentContentError,
        match="Document content is empty",
    ):
        await reprocess_text_document(
            session,
            document=document,
        )

    assert document.status == DocumentStatus.READY.value

    session.rollback.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_embedding_failure_preserves_existing_content(
    monkeypatch,
):
    document = make_text_document(
        content="Original PostgreSQL knowledge",
    )

    session = AsyncMock()
    set_status = mock_document_status(monkeypatch)

    build_chunks = AsyncMock(
        side_effect=RuntimeError("Embedding failed"),
    )
    replace_data = AsyncMock()

    monkeypatch.setattr(
        "app.services.reprocessing.build_embedded_document_chunks",
        build_chunks,
    )
    monkeypatch.setattr(
        "app.services.reprocessing.replace_document_content_and_chunks",
        replace_data,
    )

    with pytest.raises(
        RuntimeError,
        match="Embedding failed",
    ):
        await reprocess_text_document(
            session,
            document=document,
        )

    build_chunks.assert_awaited_once_with(
        document_id=document.id,
        content="Original PostgreSQL knowledge",
    )

    # No destructive replacement when embedding fails.
    replace_data.assert_not_awaited()

    session.rollback.assert_awaited_once()

    assert document.content == "Original PostgreSQL knowledge"
    assert document.status == DocumentStatus.FAILED.value

    assert set_status.await_args_list == [
        call(
            session,
            document=document,
            status=DocumentStatus.PROCESSING,
        ),
        call(
            session,
            document=document,
            status=DocumentStatus.FAILED,
        ),
    ]


@pytest.mark.anyio
async def test_atomic_replacement_failure_rolls_back(
    monkeypatch,
):
    document = make_text_document(
        content="Existing knowledge",
    )

    session = AsyncMock()
    set_status = mock_document_status(monkeypatch)

    chunks = [
        SimpleNamespace(
            document_id=document.id,
            chunk_index=0,
            content="Existing knowledge",
            embedding=[0.1, 0.2, 0.3],
        ),
    ]

    build_chunks = AsyncMock(return_value=chunks)

    replace_data = AsyncMock(
        side_effect=RuntimeError("Database commit failed"),
    )

    monkeypatch.setattr(
        "app.services.reprocessing.build_embedded_document_chunks",
        build_chunks,
    )
    monkeypatch.setattr(
        "app.services.reprocessing.replace_document_content_and_chunks",
        replace_data,
    )

    with pytest.raises(
        RuntimeError,
        match="Database commit failed",
    ):
        await reprocess_text_document(
            session,
            document=document,
        )

    build_chunks.assert_awaited_once()

    replace_data.assert_awaited_once_with(
        session,
        document=document,
        content="Existing knowledge",
        chunks=chunks,
    )

    session.rollback.assert_awaited_once()

    assert document.content == "Existing knowledge"
    assert document.status == DocumentStatus.FAILED.value

    assert set_status.await_args_list == [
        call(
            session,
            document=document,
            status=DocumentStatus.PROCESSING,
        ),
        call(
            session,
            document=document,
            status=DocumentStatus.FAILED,
        ),
    ]
