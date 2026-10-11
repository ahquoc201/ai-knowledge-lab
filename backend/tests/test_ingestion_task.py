
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

from app.tasks.ingestion import (
    _process_document_task,
    process_document_task,
)


@pytest.fixture(autouse=True)
def mock_processing_heartbeat(monkeypatch):
    async def fake_heartbeat(
        *,
        document_id,
        user_id,
        processing_run_id,
        stop_event,
    ):
        # Simulate a running heartbeat until
        # the worker signals completion.
        await stop_event.wait()

    heartbeat = AsyncMock(
        side_effect=fake_heartbeat,
    )

    monkeypatch.setattr(
        "app.tasks.ingestion.maintain_processing_heartbeat",
        heartbeat,
    )

    return heartbeat


def mock_worker_database(monkeypatch, document):
    session = AsyncMock()
    engine = SimpleNamespace(dispose=AsyncMock())

    class FakeSessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    def fake_create_async_engine(database_url, *, poolclass):
        assert database_url
        assert poolclass is NullPool
        return engine

    def fake_async_sessionmaker(
        *,
        bind,
        class_,
        expire_on_commit,
    ):
        assert bind is engine
        assert class_ is AsyncSession
        assert expire_on_commit is False
        return FakeSessionContext

    get_document = AsyncMock(return_value=document)

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
        get_document,
    )

    return session, engine, get_document


@pytest.mark.anyio
async def test_worker_processes_stored_document_with_fencing_token(
    monkeypatch,
):
    document_id = uuid4()
    user_id = uuid4()
    processing_run_id = uuid4()
    storage_key = f"{uuid4()}.txt"

    document = SimpleNamespace(
        id=document_id,
        user_id=user_id,
        storage_key=storage_key,
    )

    session, engine, get_document = mock_worker_database(
        monkeypatch,
        document,
    )

    claim = AsyncMock(return_value=processing_run_id)
    read_file = Mock(return_value=b"PostgreSQL knowledge")
    process = AsyncMock()
    mark_failed = AsyncMock()

    monkeypatch.setattr(
        "app.tasks.ingestion.claim_pending_file_processing",
        claim,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.read_stored_file",
        read_file,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.process_document",
        process,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.mark_processing_run_failed",
        mark_failed,
    )

    await _process_document_task(
        document_id=document_id,
        user_id=user_id,
    )

    get_document.assert_awaited_once_with(
        session,
        document_id=document_id,
        user_id=user_id,
    )

    claim.assert_awaited_once_with(
        session,
        document_id=document_id,
        user_id=user_id,
    )

    session.refresh.assert_awaited_once_with(document)
    read_file.assert_called_once_with(storage_key)

    process.assert_awaited_once_with(
        session,
        document=document,
        data=b"PostgreSQL knowledge",
        processing_run_id=processing_run_id,
    )

    mark_failed.assert_not_awaited()
    engine.dispose.assert_awaited_once()


@pytest.mark.anyio
async def test_worker_rejects_missing_document(monkeypatch):
    document_id = uuid4()
    user_id = uuid4()

    _, engine, _ = mock_worker_database(
        monkeypatch,
        None,
    )

    claim = AsyncMock()

    monkeypatch.setattr(
        "app.tasks.ingestion.claim_pending_file_processing",
        claim,
    )

    with pytest.raises(
        ValueError,
        match="Document not found",
    ):
        await _process_document_task(
            document_id=document_id,
            user_id=user_id,
        )

    claim.assert_not_awaited()
    engine.dispose.assert_awaited_once()


@pytest.mark.anyio
async def test_worker_rejects_missing_storage_key(
    monkeypatch,
):
    document_id = uuid4()
    user_id = uuid4()
    processing_run_id = uuid4()

    document = SimpleNamespace(
        id=document_id,
        user_id=user_id,
        storage_key=None,
    )

    session, engine, _ = mock_worker_database(
        monkeypatch,
        document,
    )

    claim = AsyncMock(return_value=processing_run_id)
    mark_failed = AsyncMock()
    process = AsyncMock()

    monkeypatch.setattr(
        "app.tasks.ingestion.claim_pending_file_processing",
        claim,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.mark_processing_run_failed",
        mark_failed,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.process_document",
        process,
    )

    with pytest.raises(
        ValueError,
        match="Document has no stored source file",
    ):
        await _process_document_task(
            document_id=document_id,
            user_id=user_id,
        )

    session.rollback.assert_awaited_once()

    mark_failed.assert_awaited_once_with(
        session,
        document_id=document_id,
        user_id=user_id,
        processing_run_id=processing_run_id,
    )

    process.assert_not_awaited()
    engine.dispose.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("Source file missing"),
        PermissionError("Source file inaccessible"),
    ],
)
async def test_worker_marks_failed_when_source_unavailable(
    monkeypatch,
    error,
):
    document_id = uuid4()
    user_id = uuid4()
    processing_run_id = uuid4()

    document = SimpleNamespace(
        id=document_id,
        user_id=user_id,
        storage_key=f"{uuid4()}.txt",
    )

    session, engine, _ = mock_worker_database(
        monkeypatch,
        document,
    )

    claim = AsyncMock(return_value=processing_run_id)
    read_file = Mock(side_effect=error)
    mark_failed = AsyncMock()
    process = AsyncMock()

    monkeypatch.setattr(
        "app.tasks.ingestion.claim_pending_file_processing",
        claim,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.read_stored_file",
        read_file,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.mark_processing_run_failed",
        mark_failed,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.process_document",
        process,
    )

    with pytest.raises(type(error)):
        await _process_document_task(
            document_id=document_id,
            user_id=user_id,
        )

    session.rollback.assert_awaited_once()

    mark_failed.assert_awaited_once_with(
        session,
        document_id=document_id,
        user_id=user_id,
        processing_run_id=processing_run_id,
    )

    process.assert_not_awaited()
    engine.dispose.assert_awaited_once()


@pytest.mark.anyio
async def test_duplicate_worker_job_is_skipped(
    monkeypatch,
):
    document_id = uuid4()
    user_id = uuid4()

    document = SimpleNamespace(
        id=document_id,
        user_id=user_id,
        storage_key=f"{uuid4()}.txt",
    )

    session, engine, _ = mock_worker_database(
        monkeypatch,
        document,
    )

    # Another worker has already claimed the job.
    claim = AsyncMock(return_value=None)
    read_file = Mock()
    process = AsyncMock()
    mark_failed = AsyncMock()

    monkeypatch.setattr(
        "app.tasks.ingestion.claim_pending_file_processing",
        claim,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.read_stored_file",
        read_file,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.process_document",
        process,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.mark_processing_run_failed",
        mark_failed,
    )

    await _process_document_task(
        document_id=document_id,
        user_id=user_id,
    )

    claim.assert_awaited_once_with(
        session,
        document_id=document_id,
        user_id=user_id,
    )

    session.refresh.assert_not_awaited()
    read_file.assert_not_called()
    process.assert_not_awaited()
    mark_failed.assert_not_awaited()

    engine.dispose.assert_awaited_once()


def test_celery_task_keeps_source_file_after_success(
    monkeypatch,
    tmp_path,
):
    document_id = uuid4()
    user_id = uuid4()

    source_file = tmp_path / "knowledge.txt"
    source_file.write_bytes(b"Persistent knowledge")

    process = AsyncMock()

    monkeypatch.setattr(
        "app.tasks.ingestion._process_document_task",
        process,
    )

    process_document_task.run(
        str(document_id),
        str(user_id),
    )

    process.assert_awaited_once_with(
        document_id=document_id,
        user_id=user_id,
    )

    assert source_file.exists()


def test_celery_task_keeps_source_file_after_failure(
    monkeypatch,
    tmp_path,
):
    document_id = uuid4()
    user_id = uuid4()

    source_file = tmp_path / "knowledge.txt"
    source_file.write_bytes(b"Persistent knowledge")

    process = AsyncMock(
        side_effect=RuntimeError("Processing failed")
    )

    monkeypatch.setattr(
        "app.tasks.ingestion._process_document_task",
        process,
    )

    with pytest.raises(
        RuntimeError,
        match="Processing failed",
    ):
        process_document_task.run(
            str(document_id),
            str(user_id),
        )

    assert source_file.exists()

@pytest.mark.anyio
async def test_processing_failure_stops_heartbeat(
    monkeypatch,
    mock_processing_heartbeat,
):
    document_id = uuid4()
    user_id = uuid4()
    processing_run_id = uuid4()

    document = SimpleNamespace(
        id=document_id,
        user_id=user_id,
        storage_key=f"{uuid4()}.txt",
    )

    session, engine, _ = mock_worker_database(
        monkeypatch,
        document,
    )

    claim = AsyncMock(return_value=processing_run_id)

    read_file = Mock(
        return_value=b"Knowledge for embedding",
    )

    process = AsyncMock(
        side_effect=RuntimeError("Embedding failed"),
    )

    monkeypatch.setattr(
        "app.tasks.ingestion.claim_pending_file_processing",
        claim,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.read_stored_file",
        read_file,
    )
    monkeypatch.setattr(
        "app.tasks.ingestion.process_document",
        process,
    )

    with pytest.raises(
        RuntimeError,
        match="Embedding failed",
    ):
        await _process_document_task(
            document_id=document_id,
            user_id=user_id,
        )

    claim.assert_awaited_once()

    process.assert_awaited_once_with(
        session,
        document=document,
        data=b"Knowledge for embedding",
        processing_run_id=processing_run_id,
    )

    mock_processing_heartbeat.assert_awaited_once()

    heartbeat_args = (
        mock_processing_heartbeat.await_args.kwargs
    )

    assert heartbeat_args["document_id"] == document_id
    assert heartbeat_args["user_id"] == user_id
    assert (
        heartbeat_args["processing_run_id"]
        == processing_run_id
    )

    # Heartbeat must be stopped even on failure.
    assert heartbeat_args["stop_event"].is_set()

    engine.dispose.assert_awaited_once()