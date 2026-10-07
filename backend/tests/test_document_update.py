from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.document_status import DocumentStatus
from app.schemas.document import DocumentUpdate
from app.services.document import (
    InvalidDocumentUpdateError,
    UnsupportedDocumentContentUpdateError,
    update_user_document,
)


@pytest.mark.anyio
async def test_update_document_title_only_preserves_status(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        title="Old title",
        content="Existing content",
        source_type="text",
        status=DocumentStatus.READY.value,
    )
    user = SimpleNamespace(id=uuid4())
    session = AsyncMock()

    async def fake_get_user_document(
        session,
        *,
        user,
        document_id,
    ):
        assert document_id == document.id
        return document

    async def fake_save_document(
        session,
        *,
        document,
    ):
        return document

    monkeypatch.setattr(
        "app.services.document.get_user_document",
        fake_get_user_document,
    )
    monkeypatch.setattr(
        "app.services.document.save_document",
        fake_save_document,
    )

    result = await update_user_document(
        session,
        user=user,
        document_id=document.id,
        data=DocumentUpdate(title="New title"),
    )

    assert result is document
    assert document.title == "New title"
    assert document.content == "Existing content"
    assert document.status == DocumentStatus.READY.value


@pytest.mark.anyio
async def test_update_document_content_marks_pending(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        title="Knowledge",
        content="Old content",
        source_type="text",
        status=DocumentStatus.READY.value,
    )
    user = SimpleNamespace(id=uuid4())
    session = AsyncMock()

    async def fake_get_user_document(
        session,
        *,
        user,
        document_id,
    ):
        return document

    async def fake_save_document(
        session,
        *,
        document,
    ):
        return document

    monkeypatch.setattr(
        "app.services.document.get_user_document",
        fake_get_user_document,
    )
    monkeypatch.setattr(
        "app.services.document.save_document",
        fake_save_document,
    )

    result = await update_user_document(
        session,
        user=user,
        document_id=document.id,
        data=DocumentUpdate(content="New content"),
    )

    assert result is document
    assert document.content == "New content"
    assert document.status == DocumentStatus.PENDING.value


@pytest.mark.anyio
async def test_update_document_content_can_be_null(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        title="Knowledge",
        content="Old content",
        source_type="text",
        status=DocumentStatus.READY.value,
    )
    user = SimpleNamespace(id=uuid4())
    session = AsyncMock()

    async def fake_get_user_document(
        session,
        *,
        user,
        document_id,
    ):
        return document

    async def fake_save_document(
        session,
        *,
        document,
    ):
        return document

    monkeypatch.setattr(
        "app.services.document.get_user_document",
        fake_get_user_document,
    )
    monkeypatch.setattr(
        "app.services.document.save_document",
        fake_save_document,
    )

    await update_user_document(
        session,
        user=user,
        document_id=document.id,
        data=DocumentUpdate(content=None),
    )

    assert document.content is None
    assert document.status == DocumentStatus.PENDING.value


@pytest.mark.anyio
async def test_update_rejects_file_document_content(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        title="Uploaded file",
        content="Extracted content",
        source_type="file",
        status=DocumentStatus.READY.value,
    )
    user = SimpleNamespace(id=uuid4())
    session = AsyncMock()

    async def fake_get_user_document(
        session,
        *,
        user,
        document_id,
    ):
        return document

    monkeypatch.setattr(
        "app.services.document.get_user_document",
        fake_get_user_document,
    )

    with pytest.raises(
        UnsupportedDocumentContentUpdateError,
        match="File document content cannot be updated",
    ):
        await update_user_document(
            session,
            user=user,
            document_id=document.id,
            data=DocumentUpdate(content="Changed"),
        )


@pytest.mark.anyio
async def test_update_rejects_null_title(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        title="Knowledge",
        content="Content",
        source_type="text",
        status=DocumentStatus.READY.value,
    )
    user = SimpleNamespace(id=uuid4())
    session = AsyncMock()

    async def fake_get_user_document(
        session,
        *,
        user,
        document_id,
    ):
        return document

    monkeypatch.setattr(
        "app.services.document.get_user_document",
        fake_get_user_document,
    )

    with pytest.raises(
        InvalidDocumentUpdateError,
        match="Document title cannot be null",
    ):
        await update_user_document(
            session,
            user=user,
            document_id=document.id,
            data=DocumentUpdate(title=None),
        )