
"""Integration tests for golden dataset reference validation."""

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.evaluation.dataset_validator import (
    GoldenDatasetReferenceError,
    validate_golden_dataset_references,
)
from app.evaluation.models import GoldenDataset, GoldenQuery
from app.models.document_chunk import DocumentChunk
from tests.test_documents import register_and_login


def create_document(
    client: TestClient,
    *,
    headers: dict[str, str],
) -> tuple[UUID, UUID]:
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Evaluation reference test",
            "content": "abcdefghij",
            "source_type": "text",
        },
    )

    assert response.status_code == 201, response.text

    body = response.json()

    return UUID(body["id"]), UUID(body["user_id"])


def create_chunks(
    client: TestClient,
    *,
    document_id: UUID,
    headers: dict[str, str],
    chunk_size: int,
    overlap: int,
) -> None:
    response = client.post(
        f"/api/v1/documents/{document_id}/chunks",
        headers=headers,
        json={
            "chunk_size": chunk_size,
            "overlap": overlap,
        },
    )

    assert response.status_code == 200, response.text


def make_dataset(
    relevant_ids: frozenset[UUID],
) -> GoldenDataset:
    return GoldenDataset(
        dataset_id="reference-test",
        version="1.0",
        cases=(
            GoldenQuery(
                case_id="q1",
                query="What information is in this document?",
                relevant_chunk_ids=relevant_ids,
            ),
        ),
    )


async def fetch_chunk_ids(
    document_id: UUID,
) -> tuple[UUID, ...]:
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )

    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with factory() as session:
            result = await session.scalars(
                select(DocumentChunk.id)
                .where(
                    DocumentChunk.document_id == document_id
                )
                .order_by(DocumentChunk.chunk_index)
            )

            return tuple(result.all())
    finally:
        await engine.dispose()


async def validate_dataset(
    dataset: GoldenDataset,
    *,
    user_id: UUID,
) -> None:
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )

    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with factory() as session:
            await validate_golden_dataset_references(
                session,
                dataset=dataset,
                user_id=user_id,
            )
    finally:
        await engine.dispose()


def test_golden_dataset_references_against_postgresql(
    client: TestClient,
):
    password = "TestPassword123!"

    token_a = register_and_login(
        client,
        email=f"evaluation-a-{uuid4()}@example.com",
        password=password,
    )

    token_b = register_and_login(
        client,
        email=f"evaluation-b-{uuid4()}@example.com",
        password=password,
    )

    headers_a = {
        "Authorization": f"Bearer {token_a}",
    }

    headers_b = {
        "Authorization": f"Bearer {token_b}",
    }

    document_a, user_a = create_document(
        client,
        headers=headers_a,
    )

    document_b, _ = create_document(
        client,
        headers=headers_b,
    )

    try:
        create_chunks(
            client,
            document_id=document_a,
            headers=headers_a,
            chunk_size=4,
            overlap=1,
        )

        create_chunks(
            client,
            document_id=document_b,
            headers=headers_b,
            chunk_size=4,
            overlap=1,
        )

        old_ids = asyncio.run(
            fetch_chunk_ids(document_a)
        )

        foreign_ids = asyncio.run(
            fetch_chunk_ids(document_b)
        )

        assert len(old_ids) == 3
        assert len(foreign_ids) == 3

        # CASE 1: Valid IDs owned by the evaluation user.
        valid_dataset = make_dataset(
            frozenset(old_ids)
        )

        asyncio.run(
            validate_dataset(
                valid_dataset,
                user_id=user_a,
            )
        )

        # CASE 2: Foreign and nonexistent chunk IDs.
        nonexistent_id = uuid4()

        invalid_ids = frozenset(
            {old_ids[0], foreign_ids[0], nonexistent_id}
        )

        invalid_dataset = make_dataset(invalid_ids)

        with pytest.raises(
            GoldenDatasetReferenceError
        ) as error:
            asyncio.run(
                validate_dataset(
                    invalid_dataset,
                    user_id=user_a,
                )
            )

        assert error.value.missing_chunk_ids == frozenset(
            {foreign_ids[0], nonexistent_id}
        )

        # CASE 3: Rechunk replaces all original chunk IDs.
        create_chunks(
            client,
            document_id=document_a,
            headers=headers_a,
            chunk_size=6,
            overlap=0,
        )

        new_ids = asyncio.run(
            fetch_chunk_ids(document_a)
        )

        assert len(new_ids) == 2
        assert set(old_ids).isdisjoint(new_ids)

        # The old golden dataset is now stale.
        with pytest.raises(
            GoldenDatasetReferenceError
        ) as stale_error:
            asyncio.run(
                validate_dataset(
                    valid_dataset,
                    user_id=user_a,
                )
            )

        assert stale_error.value.missing_chunk_ids == frozenset(
            old_ids
        )

        # A dataset referencing current chunks is valid.
        refreshed_dataset = make_dataset(
            frozenset(new_ids)
        )

        asyncio.run(
            validate_dataset(
                refreshed_dataset,
                user_id=user_a,
            )
        )

    finally:
        for document_id, headers in (
            (document_a, headers_a),
            (document_b, headers_b),
        ):
            response = client.delete(
                f"/api/v1/documents/{document_id}",
                headers=headers,
            )

            assert response.status_code == 204, response.text
