
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call
from uuid import uuid4

import pytest

from app.core.document_status import DocumentStatus
from app.services.ingestion import process_document


@pytest.mark.anyio
async def test_embedding_failure_preserves_existing_data(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        source_name="knowledge.txt",
        title="Knowledge",
        content="Original knowledge",
        status=DocumentStatus.READY.value,
    )

    session = AsyncMock()
    set_status = AsyncMock()
    replace_data = AsyncMock()
    extract_text = Mock(return_value="Updated knowledge")

    build_chunks = AsyncMock(
        side_effect=RuntimeError("Embedding unavailable")
    )

    monkeypatch.setattr(
        "app.services.ingestion.set_document_status",
        set_status,
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
        match="Embedding unavailable",
    ):
        await process_document(
            session,
            document=document,
            data=b"New source file",
        )

    extract_text.assert_called_once_with(
        filename="knowledge.txt",
        data=b"New source file",
    )

    build_chunks.assert_awaited_once_with(
        document_id=document.id,
        content="Updated knowledge",
    )

    # No replacement is attempted if embedding fails.
    replace_data.assert_not_awaited()

    # The service must roll back and record failure.
    session.rollback.assert_awaited_once()

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
            error_message="Embedding unavailable",
        ),
    ]

    assert document.content == "Original knowledge"


@pytest.mark.anyio
async def test_successful_ingestion_uses_atomic_replacement(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        source_name="knowledge.txt",
        title="Knowledge",
        content="Original knowledge",
        status=DocumentStatus.READY.value,
    )

    session = AsyncMock()
    set_status = AsyncMock()
    extract_text = Mock(return_value="Updated knowledge")

    chunks = [
        SimpleNamespace(
            document_id=document.id,
            chunk_index=0,
            content="Updated knowledge",
            embedding=[0.1, 0.2, 0.3],
        )
    ]

    build_chunks = AsyncMock(return_value=chunks)
    replace_data = AsyncMock()

    monkeypatch.setattr(
        "app.services.ingestion.set_document_status",
        set_status,
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
        data=b"Updated source",
    )

    assert result is document

    build_chunks.assert_awaited_once_with(
        document_id=document.id,
        content="Updated knowledge",
    )

    replace_data.assert_awaited_once_with(
        session,
        document=document,
        content="Updated knowledge",
        chunks=chunks,
        processing_run_id=None,
    )

    set_status.assert_awaited_once_with(
        session,
        document=document,
        status=DocumentStatus.PROCESSING,
    )

    session.rollback.assert_not_awaited()
