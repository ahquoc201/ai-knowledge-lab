
"""Unit tests for retrieval evaluation adapters."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.evaluation.adapters import SemanticSearchRetriever
from app.services.semantic_search import SemanticSearchResult


@pytest.mark.anyio
async def test_adapter_returns_ranked_chunk_ids(monkeypatch):
    session = AsyncMock()
    user_id = uuid4()

    chunk_a = SimpleNamespace(id=uuid4())
    chunk_b = SimpleNamespace(id=uuid4())
    chunk_c = SimpleNamespace(id=uuid4())

    matches = [
        SemanticSearchResult(
            chunk=chunk_b,
            similarity=0.95,
        ),
        SemanticSearchResult(
            chunk=chunk_a,
            similarity=0.82,
        ),
        SemanticSearchResult(
            chunk=chunk_c,
            similarity=0.60,
        ),
    ]

    search = AsyncMock(return_value=matches)

    monkeypatch.setattr(
        "app.evaluation.adapters.semantic_search",
        search,
    )

    retriever = SemanticSearchRetriever(
        session,
        user_id=user_id,
    )

    result = await retriever(
        "What is PostgreSQL?",
        3,
    )

    # Preserve the ranking returned by semantic search.
    assert result == [
        chunk_b.id,
        chunk_a.id,
        chunk_c.id,
    ]

    # Verify the complete search contract.
    search.assert_awaited_once_with(
        session,
        user_id=user_id,
        query="What is PostgreSQL?",
        limit=3,
    )


@pytest.mark.anyio
async def test_adapter_handles_empty_search_results(
    monkeypatch,
):
    session = AsyncMock()
    user_id = uuid4()

    search = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "app.evaluation.adapters.semantic_search",
        search,
    )

    retriever = SemanticSearchRetriever(
        session,
        user_id=user_id,
    )

    result = await retriever(
        "Unknown question",
        5,
    )

    assert result == []

    search.assert_awaited_once_with(
        session,
        user_id=user_id,
        query="Unknown question",
        limit=5,
    )


@pytest.mark.anyio
async def test_adapter_propagates_search_failure(
    monkeypatch,
):
    session = AsyncMock()
    user_id = uuid4()

    search = AsyncMock(
        side_effect=RuntimeError(
            "Vector database unavailable"
        ),
    )

    monkeypatch.setattr(
        "app.evaluation.adapters.semantic_search",
        search,
    )

    retriever = SemanticSearchRetriever(
        session,
        user_id=user_id,
    )

    with pytest.raises(
        RuntimeError,
        match="Vector database unavailable",
    ):
        await retriever(
            "PostgreSQL",
            5,
        )

    search.assert_awaited_once()
