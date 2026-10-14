from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.celery_app import celery_app
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def configure_test_celery_broker():
    """Configure Celery to use an isolated in-memory broker during test execution.

    This guarantees tests never inadvertently communicate with or leak tasks
    into the development Redis broker.
    """
    original_broker = celery_app.conf.broker_url
    celery_app.conf.broker_url = "memory://"
    yield
    celery_app.conf.broker_url = original_broker


@pytest.fixture(autouse=True)
def isolate_celery_tasks(monkeypatch):
    """Isolate background task scheduling across all unit and API tests.

    By default, task.delay() is intercepted at the API boundary so tests creating
    documents do not trigger unintended background processing. Tests that specifically
    verify scheduling semantics can override or inspect this mock.
    """
    mock_delay = MagicMock(name="process_document_task.delay")
    monkeypatch.setattr(
        "app.api.v1.documents.process_document_task.delay",
        mock_delay,
    )
    return mock_delay


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client