from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.tasks.ingestion import _process_document_task, process_document_task


@pytest.mark.anyio
async def test_process_document_task_processes_existing_document(
    monkeypatch,
    tmp_path,
):
    document_id = uuid4()
    user_id = uuid4()

    file_path = tmp_path / "knowledge.txt"
    file_path.write_bytes(b"PostgreSQL knowledge")

    document = SimpleNamespace(
        id=document_id,
        user_id=user_id,
    )
    session = AsyncMock()

    class FakeEngine:
        def __init__(self):
            self.disposed = False

        async def dispose(self):
            self.disposed = True

    class FakeSessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(
            self,
            exc_type,
            exc,
            traceback,
        ):
            return False

    fake_engine = FakeEngine()

    def fake_create_async_engine(
        database_url,
        *,
        poolclass,
    ):
        assert database_url
        assert poolclass is not None
        return fake_engine

    def fake_async_sessionmaker(
        *,
        bind,
        class_,
        expire_on_commit,
    ):
        assert bind is fake_engine
        assert class_ is not None
        assert expire_on_commit is False

        return FakeSessionContext

    async def fake_get_document_by_id_for_user(
        session_arg,
        *,
        document_id: object,
        user_id: object,
    ):
        assert session_arg is session
        assert document_id == document.id
        assert user_id == document.user_id
        return document

    async def fake_process_document(
        session_arg,
        *,
        document: object,
        data: bytes,
    ):
        assert session_arg is session
        assert document is not None
        assert data == b"PostgreSQL knowledge"

    monkeypatch.setattr(
        "app.tasks.ingestion.create_async_engine",
        fake_create_async_engine,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.async_sessionmaker",
        fake_async_sessionmaker,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.get_document_by_id_for_user",
        fake_get_document_by_id_for_user,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.process_document",
        fake_process_document,
    )

    await _process_document_task(
        document_id=document_id,
        user_id=user_id,
        file_path=file_path,
    )

    assert fake_engine.disposed is True


@pytest.mark.anyio
async def test_process_document_task_fails_when_document_not_found(
    monkeypatch,
    tmp_path,
):
    document_id = uuid4()
    user_id = uuid4()

    file_path = tmp_path / "knowledge.txt"
    file_path.write_bytes(b"PostgreSQL knowledge")

    session = AsyncMock()

    class FakeEngine:
        def __init__(self):
            self.disposed = False

        async def dispose(self):
            self.disposed = True

    class FakeSessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(
            self,
            exc_type,
            exc,
            traceback,
        ):
            return False

    fake_engine = FakeEngine()

    monkeypatch.setattr(
        "app.tasks.ingestion.create_async_engine",
        lambda *args, **kwargs: fake_engine,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.async_sessionmaker",
        lambda **kwargs: FakeSessionContext,
    )

    async def fake_get_document_by_id_for_user(
        session_arg,
        *,
        document_id,
        user_id,
    ):
        return None

    monkeypatch.setattr(
        "app.tasks.ingestion.get_document_by_id_for_user",
        fake_get_document_by_id_for_user,
    )

    with pytest.raises(
        ValueError,
        match="Document not found",
    ):
        await _process_document_task(
            document_id=document_id,
            user_id=user_id,
            file_path=file_path,
        )

    assert fake_engine.disposed is True

def test_process_document_task_deletes_file_after_success(
    monkeypatch,
    tmp_path,
):
    document_id = uuid4()
    user_id = uuid4()

    file_path = tmp_path / "knowledge.txt"
    file_path.write_bytes(b"PostgreSQL knowledge")

    async def fake_process_document_task(
        *,
        document_id,
        user_id,
        file_path,
    ):
        return None

    monkeypatch.setattr(
        "app.tasks.ingestion._process_document_task",
        fake_process_document_task,
    )

    process_document_task.run(
        str(document_id),
        str(user_id),
        str(file_path),
    )

    assert not file_path.exists()


def test_process_document_task_deletes_file_after_failure(
    monkeypatch,
    tmp_path,
):
    document_id = uuid4()
    user_id = uuid4()

    file_path = tmp_path / "knowledge.txt"
    file_path.write_bytes(b"PostgreSQL knowledge")

    async def fake_process_document_task(
        *,
        document_id,
        user_id,
        file_path,
    ):
        raise RuntimeError("Processing failed")

    monkeypatch.setattr(
        "app.tasks.ingestion._process_document_task",
        fake_process_document_task,
    )

    with pytest.raises(
        RuntimeError,
        match="Processing failed",
    ):
        process_document_task.run(
            str(document_id),
            str(user_id),
            str(file_path),
        )

    assert not file_path.exists()