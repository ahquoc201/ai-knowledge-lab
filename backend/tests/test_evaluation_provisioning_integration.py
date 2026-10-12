
"""Integration tests for retrieval fixture provisioning."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.embedding import EMBEDDING_DIMENSIONS
from app.evaluation.dataset_validator import (
    validate_golden_dataset_references,
)
from app.evaluation.fixture_manifest import load_fixture_manifest
from app.evaluation.fixture_provisioner import (
    provision_retrieval_fixture,
)
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User


@pytest.mark.anyio
async def test_provision_fixture_and_cleanup():
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "datasets"
        / "evaluation"
        / "retrieval_fixtures.json"
    )

    manifest = load_fixture_manifest(fixture_path)

    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )

    try:
        async with provision_retrieval_fixture(
            engine=engine,
            manifest=manifest,
            allow_fixture_writes=True,
        ) as fixture:
            user_id = fixture.user_id
            document_ids = fixture.document_ids

            assert len(document_ids) == 4
            assert len(set(document_ids)) == 4
            assert len(fixture.dataset.cases) == 8

            async with AsyncSession(engine) as session:
                user = await session.get(User, user_id)

                assert user is not None
                assert user.is_active is False

                documents = list(
                    (
                        await session.scalars(
                            select(Document).where(
                                Document.user_id == user_id
                            )
                        )
                    ).all()
                )

                assert len(documents) == 4
                assert {doc.id for doc in documents} == set(
                    document_ids
                )

                chunks = list(
                    (
                        await session.scalars(
                            select(DocumentChunk).where(
                                DocumentChunk.document_id.in_(
                                    document_ids
                                )
                            )
                        )
                    ).all()
                )

                assert len(chunks) == 4

                assert all(
                    chunk.embedding is not None
                    and len(chunk.embedding) == EMBEDDING_DIMENSIONS
                    for chunk in chunks
                )

                # All golden labels must refer to real,
                # user-owned chunks.
                await validate_golden_dataset_references(
                    session,
                    dataset=fixture.dataset,
                    user_id=user_id,
                )

        # The context manager must remove its own resources.
        async with AsyncSession(engine) as session:
            assert await session.get(User, user_id) is None

            remaining_documents = await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.user_id == user_id)
            )

            remaining_chunks = await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(
                    DocumentChunk.document_id.in_(
                        document_ids
                    )
                )
            )

            assert remaining_documents == 0
            assert remaining_chunks == 0

    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_provisioning_failure_rolls_back_all_resources(
    monkeypatch,
):
    """A failure after database flush must roll back everything."""

    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "datasets"
        / "evaluation"
        / "retrieval_fixtures.json"
    )

    manifest = load_fixture_manifest(fixture_path)

    # Make the generated evaluation user ID predictable.
    evaluation_user_id = uuid4()
    real_uuid4 = uuid4
    first_call = True

    def fake_uuid4():
        nonlocal first_call

        if first_call:
            first_call = False
            return evaluation_user_id

        return real_uuid4()

    monkeypatch.setattr(
        "app.evaluation.fixture_provisioner.uuid4",
        fake_uuid4,
    )

    created_document_ids = []

    # Avoid loading the embedding model.
    # This test focuses exclusively on database atomicity.
    async def fake_build_chunks(
        *,
        document_id,
        content,
    ):
        created_document_ids.append(document_id)

        return [
            DocumentChunk(
                document_id=document_id,
                chunk_index=0,
                content=content,
                char_start=0,
                char_end=len(content),
                embedding=[0.1] * EMBEDDING_DIMENSIONS,
            )
        ]

    monkeypatch.setattr(
        "app.evaluation.fixture_provisioner."
        "build_embedded_document_chunks",
        fake_build_chunks,
    )

    # Inject a failure AFTER the database has flushed
    # the user, documents and chunks.
    def fail_build_golden_dataset(
        *,
        manifest,
        chunk_ids_by_document_key,
    ):
        raise RuntimeError(
            "Simulated failure after database flush"
        )

    monkeypatch.setattr(
        "app.evaluation.fixture_provisioner."
        "build_fixture_golden_dataset",
        fail_build_golden_dataset,
    )

    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )

    try:
        with pytest.raises(
            RuntimeError,
            match="Simulated failure after database flush",
        ):
            async with provision_retrieval_fixture(
                engine=engine,
                manifest=manifest,
                allow_fixture_writes=True,
            ):
                pytest.fail(
                    "Provisioning must not succeed"
                )

        assert len(created_document_ids) == len(
            manifest.documents
        )

        # Open a fresh connection to verify the rollback.
        async with AsyncSession(engine) as session:
            user = await session.get(
                User,
                evaluation_user_id,
            )

            remaining_documents = await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(
                    Document.user_id == evaluation_user_id
                )
            )

            remaining_chunks = await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(
                    DocumentChunk.document_id.in_(
                        created_document_ids
                    )
                )
            )

        assert user is None
        assert remaining_documents == 0
        assert remaining_chunks == 0

    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_cleanup_when_evaluation_raises(
    monkeypatch,
):
    """Committed fixture resources are removed if evaluation fails."""

    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "datasets"
        / "evaluation"
        / "retrieval_fixtures.json"
    )

    manifest = load_fixture_manifest(fixture_path)

    # Avoid running the real embedding model.
    # This test focuses on cleanup after a successful commit.
    async def fake_build_chunks(
        *,
        document_id,
        content,
    ):
        return [
            DocumentChunk(
                document_id=document_id,
                chunk_index=0,
                content=content,
                char_start=0,
                char_end=len(content),
                embedding=[0.1] * EMBEDDING_DIMENSIONS,
            )
        ]

    monkeypatch.setattr(
        "app.evaluation.fixture_provisioner."
        "build_embedded_document_chunks",
        fake_build_chunks,
    )

    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )

    user_id = None
    document_ids = ()

    try:
        with pytest.raises(
            RuntimeError,
            match="Simulated evaluation failure",
        ):
            async with provision_retrieval_fixture(
                engine=engine,
                manifest=manifest,
                allow_fixture_writes=True,
            ) as fixture:
                user_id = fixture.user_id
                document_ids = fixture.document_ids

                # Provisioning has committed successfully.
                # A separate session must see the new data.
                async with AsyncSession(engine) as session:
                    user = await session.get(User, user_id)

                    document_count = await session.scalar(
                        select(func.count())
                        .select_from(Document)
                        .where(Document.user_id == user_id)
                    )

                    assert user is not None
                    assert document_count == len(
                        manifest.documents
                    )

                # Simulate a failure during retrieval evaluation.
                raise RuntimeError(
                    "Simulated evaluation failure"
                )

        assert user_id is not None
        assert len(document_ids) == len(manifest.documents)

        # Even though evaluation failed, cleanup must
        # remove the committed evaluation corpus.
        async with AsyncSession(engine) as session:
            user = await session.get(User, user_id)

            document_count = await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.user_id == user_id)
            )

            chunk_count = await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(
                    DocumentChunk.document_id.in_(
                        document_ids
                    )
                )
            )

            assert user is None
            assert document_count == 0
            assert chunk_count == 0

    finally:
        await engine.dispose()
