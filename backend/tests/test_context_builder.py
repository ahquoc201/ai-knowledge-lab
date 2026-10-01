from uuid import uuid4

from app.models.document_chunk import DocumentChunk
from app.services.context_builder import build_retrieval_context
from app.services.semantic_search import SemanticSearchResult


def test_build_retrieval_context():
    document_id = uuid4()

    chunk_a = DocumentChunk(
        id=uuid4(),
        document_id=document_id,
        chunk_index=0,
        content="PostgreSQL hỗ trợ transaction.",
        char_start=0,
        char_end=32,
    )

    chunk_b = DocumentChunk(
        id=uuid4(),
        document_id=document_id,
        chunk_index=1,
        content="pgvector hỗ trợ semantic search.",
        char_start=33,
        char_end=67,
    )

    results = [
        SemanticSearchResult(
            chunk=chunk_a,
            similarity=0.91,
        ),
        SemanticSearchResult(
            chunk=chunk_b,
            similarity=0.84,
        ),
    ]

    context = build_retrieval_context(results)

    assert context.text == (
        "[Source 1]\n"
        "PostgreSQL hỗ trợ transaction.\n\n"
        "[Source 2]\n"
        "pgvector hỗ trợ semantic search."
    )

    assert len(context.sources) == 2

    assert context.sources[0].source_index == 1
    assert context.sources[0].chunk_id == chunk_a.id
    assert context.sources[0].chunk_index == 0
    assert context.sources[0].similarity == 0.91

    assert context.sources[1].source_index == 2
    assert context.sources[1].chunk_id == chunk_b.id
    assert context.sources[1].chunk_index == 1
    assert context.sources[1].similarity == 0.84


def test_build_retrieval_context_empty():
    context = build_retrieval_context([])

    assert context.text == ""
    assert context.sources == []