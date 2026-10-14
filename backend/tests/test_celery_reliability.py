"""Tests for Celery reliability, retry classification, and test isolation."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.file_extractor import FileExtractionError, UnsupportedFileTypeError
from app.tasks.ingestion import (
    DocumentNotFoundError,
    process_document_task,
)


def test_celery_task_discards_missing_document_without_retry(monkeypatch):
    """When a document is not found, Celery should discard the task without retrying."""
    document_id = uuid4()
    user_id = uuid4()

    mock_process = AsyncMock(
        side_effect=DocumentNotFoundError(f"Document not found: {document_id}")
    )
    monkeypatch.setattr(
        "app.tasks.ingestion._process_document_task",
        mock_process,
    )

    mock_retry = MagicMock()
    monkeypatch.setattr(process_document_task, "retry", mock_retry)

    res = process_document_task.apply(args=[str(document_id), str(user_id)])

    assert res.successful()
    mock_retry.assert_not_called()
    mock_process.assert_awaited_once()


@pytest.mark.parametrize(
    "error",
    [
        UnsupportedFileTypeError("Unsupported file format: .xyz"),
        FileExtractionError("PDF file contains no extractable text"),
        ValueError("Document content is empty"),
    ],
)
def test_celery_task_does_not_retry_permanent_business_errors(monkeypatch, error):
    """Permanent extraction/input errors should not trigger Celery retries."""
    document_id = uuid4()
    user_id = uuid4()

    mock_process = AsyncMock(side_effect=error)
    monkeypatch.setattr(
        "app.tasks.ingestion._process_document_task",
        mock_process,
    )

    mock_retry = MagicMock()
    monkeypatch.setattr(process_document_task, "retry", mock_retry)

    res = process_document_task.apply(args=[str(document_id), str(user_id)])

    assert res.successful()
    mock_retry.assert_not_called()
    mock_process.assert_awaited_once()


@pytest.mark.parametrize(
    ("retries", "expected_countdown"),
    [
        (0, 5),   # 5 * 2^0 = 5
        (1, 10),  # 5 * 2^1 = 10
        (2, 20),  # 5 * 2^2 = 20
    ],
)
def test_celery_task_retries_transient_errors_with_exponential_backoff(
    monkeypatch,
    retries,
    expected_countdown,
):
    """Transient failures (network/db timeouts) must trigger exponential backoff retry."""
    document_id = uuid4()
    user_id = uuid4()
    transient_err = ConnectionError("PostgreSQL connection timed out")

    mock_process = AsyncMock(side_effect=transient_err)
    monkeypatch.setattr(
        "app.tasks.ingestion._process_document_task",
        mock_process,
    )

    mock_retry = MagicMock()
    monkeypatch.setattr(process_document_task, "retry", mock_retry)

    process_document_task.apply(
        args=[str(document_id), str(user_id)],
        retries=retries,
    )

    mock_retry.assert_called_once_with(
        exc=transient_err,
        countdown=expected_countdown,
    )


def test_test_isolation_celery_broker_is_in_memory():
    """Verify that Celery in tests uses an isolated in-memory transport."""
    from app.core.celery_app import celery_app
    assert celery_app.conf.broker_url.startswith("memory://")
