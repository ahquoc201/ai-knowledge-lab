
"""Integration tests for the retrieval evaluation service."""

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.evaluation.dataset_validator import (
    GoldenDatasetReferenceError,
)
from app.evaluation.models import GoldenDataset, GoldenQuery
from app.evaluation.service import evaluate_semantic_search
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk import replace_document_chunks
from app.services.semantic_search import SemanticSearchResult
from tests.test_documents import register_and_login


async def run_evaluation_checks(
    *,
    document_id: UUID,
    user_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )

    try:
        # Get an existing chunk ID from PostgreSQL.
        async with AsyncSession(engine) as session:
            chunk_id = await session.scalar(
                select(DocumentChunk.id)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
                .limit(1)
            )

        assert chunk_id is not None

        dataset = GoldenDataset(
            dataset_id="evaluation-service-test",
            version="1.0",
            cases=(
                GoldenQuery(
                    case_id="q1",
                    query="What is in the document?",
                    relevant_chunk_ids=frozenset({chunk_id}),
                ),
            ),
        )

        observed_transactions: list[tuple[str, str]] = []

        async def fake_semantic_search(
            session: AsyncSession,
            *,
            user_id: UUID,
            query: str,
            limit: int,
        ) -> list[SemanticSearchResult]:
            assert query == "What is in the document?"
            assert limit == 1

            # Inspect the actual PostgreSQL transaction.
            isolation = await session.scalar(
                text("SHOW transaction_isolation")
            )

            read_only = await session.scalar(
                text("SHOW transaction_read_only")
            )

            observed_transactions.append(
                (isolation, read_only)
            )

            # Use the real DB and preserve user isolation.
            chunks = await session.scalars(
                select(DocumentChunk)
                .join(
                    Document,
                    Document.id == DocumentChunk.document_id,
                )
                .where(
                    Document.user_id == user_id,
                    DocumentChunk.document_id == document_id,
                )
                .order_by(DocumentChunk.chunk_index)
                .limit(limit)
            )

            return [
                SemanticSearchResult(
                    chunk=chunk,
                    similarity=0.95,
                )
                for chunk in chunks.all()
            ]

        monkeypatch.setattr(
            "app.evaluation.adapters.semantic_search",
            fake_semantic_search,
        )

        # Valid dataset owned by the evaluation user.
        report = await evaluate_semantic_search(
            engine=engine,
            dataset=dataset,
            user_id=user_id,
            k=1,
        )

        assert report.dataset_id == "evaluation-service-test"
        assert report.k == 1
        assert len(report.results) == 1

        assert report.results[0].ranked_chunk_ids == (
            chunk_id,
        )

        assert report.mean_precision_at_k == 1.0
        assert report.mean_recall_at_k == 1.0
        assert report.mrr_at_k == 1.0

        # Verify transaction settings from PostgreSQL.
        assert observed_transactions == [
            ("repeatable read", "on"),
        ]

        # Another user must not evaluate this dataset.
        with pytest.raises(GoldenDatasetReferenceError):
            await evaluate_semantic_search(
                engine=engine,
                dataset=dataset,
                user_id=uuid4(),
                k=1,
            )

        # Validator must reject the request before retrieval.
        assert len(observed_transactions) == 1

    finally:
        await engine.dispose()


def test_evaluation_service_transaction_and_user_isolation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    token = register_and_login(
        client,
        email=f"evaluation-service-{uuid4()}@example.com",
        password="TestPassword123!",
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    create_response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Evaluation service integration",
            "content": "abcdefghij",
            "source_type": "text",
        },
    )

    assert create_response.status_code == 201
    document = create_response.json()

    document_id = UUID(document["id"])
    user_id = UUID(document["user_id"])

    try:
        chunk_response = client.post(
            f"/api/v1/documents/{document_id}/chunks",
            headers=headers,
            json={
                "chunk_size": 4,
                "overlap": 1,
            },
        )

        assert chunk_response.status_code == 200
        assert len(chunk_response.json()) == 3

        asyncio.run(
            run_evaluation_checks(
                document_id=document_id,
                user_id=user_id,
                monkeypatch=monkeypatch,
            )
        )

    finally:
        delete_response = client.delete(
            f"/api/v1/documents/{document_id}",
            headers=headers,
        )

        assert delete_response.status_code == 204



def test_evaluation_snapshot_remains_stable_during_rechunk(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    token = register_and_login(
        client,
        email=f"snapshot-{uuid4()}@example.com",
        password="TestPassword123!",
    )
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "title": "Snapshot consistency",
            "content": "abcdefghij",
            "source_type": "text",
        },
    )
    assert response.status_code == 201, response.text

    document_id = UUID(response.json()["id"])
    user_id = UUID(response.json()["user_id"])

    try:
        response = client.post(
            f"/api/v1/documents/{document_id}/chunks",
            headers=headers,
            json={"chunk_size": 4, "overlap": 1},
        )
        assert response.status_code == 200, response.text

        original_id = UUID(response.json()[0]["id"])

        async def run_checks():
            engine = create_async_engine(
                get_settings().database_url,
                poolclass=NullPool,
            )
            observed_ids = []

            try:
                async def fake_search(
                    session,
                    *,
                    user_id,
                    query,
                    limit,
                ):
                    result = await session.scalars(
                        select(DocumentChunk)
                        .join(
                            Document,
                            Document.id == DocumentChunk.document_id,
                        )
                        .where(
                            Document.user_id == user_id,
                            DocumentChunk.document_id == document_id,
                        )
                        .order_by(DocumentChunk.chunk_index)
                        .limit(limit)
                    )
                    chunks = list(result.all())
                    assert chunks

                    observed_ids.append(chunks[0].id)

                    if query == "before":
                        # Replace chunks in a separate transaction.
                        async with AsyncSession(
                            engine,
                            expire_on_commit=False,
                        ) as writer:
                            replacement = DocumentChunk(
                                document_id=document_id,
                                chunk_index=0,
                                content="Replacement knowledge",
                                char_start=0,
                                char_end=21,
                            )
                            await asyncio.wait_for(
                                replace_document_chunks(
                                    writer,
                                    document_id=document_id,
                                    chunks=[replacement],
                                ),
                                timeout=10,
                            )

                    return [
                        SemanticSearchResult(
                            chunk=chunks[0],
                            similarity=0.95,
                        )
                    ]

                monkeypatch.setattr(
                    "app.evaluation.adapters.semantic_search",
                    fake_search,
                )

                dataset = GoldenDataset(
                    dataset_id="snapshot-test",
                    version="1.0",
                    cases=(
                        GoldenQuery(
                            case_id="q1",
                            query="before",
                            relevant_chunk_ids=frozenset(
                                {original_id}
                            ),
                        ),
                        GoldenQuery(
                            case_id="q2",
                            query="after",
                            relevant_chunk_ids=frozenset(
                                {original_id}
                            ),
                        ),
                    ),
                )

                report = await evaluate_semantic_search(
                    engine=engine,
                    dataset=dataset,
                    user_id=user_id,
                    k=1,
                )

                # Both queries see the same original snapshot.
                assert observed_ids == [
                    original_id,
                    original_id,
                ]
                assert report.mean_recall_at_k == 1.0
                assert report.mrr_at_k == 1.0

                # A new transaction sees the replacement.
                async with AsyncSession(engine) as session:
                    current_ids = list(
                        (
                            await session.scalars(
                                select(DocumentChunk.id).where(
                                    DocumentChunk.document_id
                                    == document_id
                                )
                            )
                        ).all()
                    )

                assert len(current_ids) == 1
                assert original_id not in current_ids

            finally:
                await engine.dispose()

        asyncio.run(run_checks())

    finally:
        response = client.delete(
            f"/api/v1/documents/{document_id}",
            headers=headers,
        )
        assert response.status_code == 204, response.text
