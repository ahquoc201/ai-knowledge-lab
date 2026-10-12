
"""Unit tests for evaluation fixture provisioning safety."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.evaluation.fixture_manifest import RetrievalFixtureManifest
from app.evaluation.fixture_provisioner import (
    provision_retrieval_fixture,
)


def make_manifest() -> RetrievalFixtureManifest:
    return RetrievalFixtureManifest.model_validate(
        {
            "dataset_id": "provisioner-test",
            "version": "1.0",
            "documents": [
                {
                    "key": "postgresql",
                    "title": "PostgreSQL",
                    "content": "PostgreSQL supports ACID transactions.",
                }
            ],
            "cases": [
                {
                    "case_id": "q1",
                    "query": "What supports ACID?",
                    "relevant_document_keys": ["postgresql"],
                }
            ],
        }
    )


@pytest.fixture
def development_environment(monkeypatch):
    monkeypatch.setattr(
        "app.evaluation.fixture_provisioner.get_settings",
        lambda: SimpleNamespace(app_env="development"),
    )

    # Avoid expensive password hashing in safety unit tests.
    monkeypatch.setattr(
        "app.evaluation.fixture_provisioner.hash_password",
        lambda password: "test-password-hash",
    )


@pytest.mark.anyio
async def test_provisioning_requires_explicit_approval(
    development_environment,
    monkeypatch,
):
    build_chunks = AsyncMock()

    monkeypatch.setattr(
        "app.evaluation.fixture_provisioner."
        "build_embedded_document_chunks",
        build_chunks,
    )

    with pytest.raises(
        PermissionError,
        match="explicit approval",
    ):
        async with provision_retrieval_fixture(
            engine=None,
            manifest=make_manifest(),
        ):
            pytest.fail("Provisioning must be rejected")

    build_chunks.assert_not_awaited()


@pytest.mark.anyio
async def test_provisioning_rejected_in_production(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.evaluation.fixture_provisioner.get_settings",
        lambda: SimpleNamespace(app_env="production"),
    )

    build_chunks = AsyncMock()

    monkeypatch.setattr(
        "app.evaluation.fixture_provisioner."
        "build_embedded_document_chunks",
        build_chunks,
    )

    with pytest.raises(
        PermissionError,
        match="limited to development/test",
    ):
        async with provision_retrieval_fixture(
            engine=None,
            manifest=make_manifest(),
            allow_fixture_writes=True,
        ):
            pytest.fail("Production must be rejected")

    build_chunks.assert_not_awaited()


@pytest.mark.anyio
async def test_embedding_failure_stops_provisioning(
    development_environment,
    monkeypatch,
):
    build_chunks = AsyncMock(
        side_effect=RuntimeError("Embedding unavailable"),
    )

    monkeypatch.setattr(
        "app.evaluation.fixture_provisioner."
        "build_embedded_document_chunks",
        build_chunks,
    )

    with pytest.raises(
        RuntimeError,
        match="Embedding unavailable",
    ):
        async with provision_retrieval_fixture(
            engine=None,
            manifest=make_manifest(),
            allow_fixture_writes=True,
        ):
            pytest.fail("Provisioning must not succeed")

    build_chunks.assert_awaited_once()


@pytest.mark.anyio
async def test_empty_chunks_rejected_before_database_write(
    development_environment,
    monkeypatch,
):
    build_chunks = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.evaluation.fixture_provisioner."
        "build_embedded_document_chunks",
        build_chunks,
    )

    with pytest.raises(
        ValueError,
        match="Fixture document produced no chunks: postgresql",
    ):
        async with provision_retrieval_fixture(
            engine=None,
            manifest=make_manifest(),
            allow_fixture_writes=True,
        ):
            pytest.fail("Empty chunks must be rejected")

    build_chunks.assert_awaited_once()
