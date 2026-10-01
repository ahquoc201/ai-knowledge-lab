from uuid import uuid4

import pytest

from app.models.document_chunk import DocumentChunk
from app.services.retrieval import retrieve_context
from app.services.semantic_search import SemanticSearchResult


@pytest.mark.anyio
async def test_retrieve_context_builds_ranked_sources(
    monkeypatch,
):
    user_id = uuid4()
    document_id = uuid4()

    database_chunk = DocumentChunk(
        id=uuid4(),
        document_id=document_id,
        chunk_index=0,
        content=(
            "PostgreSQL là hệ quản trị cơ sở dữ liệu quan hệ. "
            "Nó hỗ trợ SQL và transaction."
        ),
        char_start=0,
        char_end=86,
    )

    food_chunk = DocumentChunk(
        id=uuid4(),
        document_id=uuid4(),
        chunk_index=0,
        content=(
            "Phở bò là món ăn Việt Nam gồm bánh phở, "
            "thịt bò và nước dùng."
        ),
        char_start=0,
        char_end=72,
    )

    async def fake_semantic_search(
        session,
        *,
        user_id,
        query,
        limit,
    ):
        return [
            SemanticSearchResult(
                chunk=database_chunk,
                similarity=0.92,
            ),
            SemanticSearchResult(
                chunk=food_chunk,
                similarity=0.31,
            ),
        ]

    monkeypatch.setattr(
        "app.services.retrieval.semantic_search",
        fake_semantic_search,
    )

    context = await retrieve_context(
        None,
        user_id=user_id,
        query="PostgreSQL dùng để quản lý dữ liệu như thế nào?",
        limit=2,
    )

    assert len(context.sources) == 2

    assert context.sources[0].document_id == document_id
    assert context.sources[0].source_index == 1
    assert context.sources[0].similarity == 0.92

    assert context.sources[1].source_index == 2
    assert context.sources[1].similarity == 0.31

    assert "[Source 1]" in context.text
    assert "PostgreSQL" in context.text

    assert (
        context.sources[0].similarity
        >= context.sources[1].similarity
    )