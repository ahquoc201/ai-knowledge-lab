from uuid import uuid4

import pytest

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


def make_search_results(*contents: str):
    """Create ranked search results without a database."""

    document_id = uuid4()
    results = []

    for index, content in enumerate(contents):
        chunk = DocumentChunk(
            id=uuid4(),
            document_id=document_id,
            chunk_index=index,
            content=content,
            char_start=0,
            char_end=len(content),
        )

        results.append(
            SemanticSearchResult(
                chunk=chunk,
                similarity=0.9 - index * 0.1,
            )
        )

    return results


def test_context_budget_keeps_sources_when_they_fit():
    results = make_search_results(
        "abcdefghij",
        "klmnopqrst",
    )

    context = build_retrieval_context(
        results,
        max_chars=44,
    )

    assert context.text == (
        "[Source 1]\nabcdefghij\n\n"
        "[Source 2]\nklmnopqrst"
    )
    assert len(context.text) == 44
    assert len(context.sources) == 2


def test_context_budget_truncates_large_chunk():
    results = make_search_results("abcdefghij")

    context = build_retrieval_context(
        results,
        max_chars=15,
    )

    assert context.text == "[Source 1]\nabcd"
    assert len(context.text) == 15

    assert len(context.sources) == 1
    assert context.sources[0].content == "abcd"
    assert context.sources[0].source_index == 1


def test_context_budget_omits_lower_ranked_source():
    results = make_search_results(
        "abcdefghij",
        "klmnopqrst",
    )

    context = build_retrieval_context(
        results,
        max_chars=26,
    )

    assert context.text == "[Source 1]\nabcdefghij"
    assert len(context.sources) == 1
    assert context.sources[0].source_index == 1
    assert "[Source 2]" not in context.text


def test_context_budget_too_small_for_source():
    results = make_search_results("abcdefghij")

    context = build_retrieval_context(
        results,
        max_chars=11,
    )

    assert context.text == ""
    assert context.sources == []


def test_context_budget_has_default_limit():
    results = make_search_results("x" * 8100)

    context = build_retrieval_context(results)

    assert len(context.text) == 8000
    assert len(context.sources) == 1

    # The source must reflect exactly what the LLM receives.
    assert context.sources[0].content == "x" * 7989


@pytest.mark.parametrize(
    ("max_chars", "expected_error"),
    [
        (0, ValueError),
        (-1, ValueError),
        (True, TypeError),
        (1.5, TypeError),
    ],
)
def test_context_budget_rejects_invalid_values(
    max_chars,
    expected_error,
):
    results = make_search_results("PostgreSQL")

    with pytest.raises(expected_error):
        build_retrieval_context(
            results,
            max_chars=max_chars,
        )


@pytest.mark.parametrize(
    ("max_chars", "expected_text", "expected_content"),
    [
        (11, "", None),
        (12, "[Source 1]\na", "a"),
        (20, "[Source 1]\nabcdefghi", "abcdefghi"),
        (21, "[Source 1]\nabcdefghij", "abcdefghij"),
    ],
)
def test_context_budget_exact_character_boundaries(
    max_chars,
    expected_text,
    expected_content,
):
    results = make_search_results("abcdefghij")

    context = build_retrieval_context(
        results,
        max_chars=max_chars,
    )

    assert context.text == expected_text
    assert len(context.text) <= max_chars

    if expected_content is None:
        assert context.sources == []
    else:
        assert len(context.sources) == 1
        assert context.sources[0].content == expected_content


def test_context_budget_skips_blank_chunks_and_renumbers_sources():
    results = make_search_results(
        "   ",
        "PostgreSQL",
        "\n\t",
        "Redis",
    )

    context = build_retrieval_context(results)

    assert context.text == (
        "[Source 1]\nPostgreSQL\n\n"
        "[Source 2]\nRedis"
    )

    assert len(context.sources) == 2
    assert [source.source_index for source in context.sources] == [
        1,
        2,
    ]

    assert context.sources[0].chunk_id == results[1].chunk.id
    assert context.sources[1].chunk_id == results[3].chunk.id


@pytest.mark.parametrize(
    ("max_chars", "expected_second_content"),
    [
        (29, "xy"),
        (30, "xyz"),
    ],
)
def test_context_budget_counts_separator_between_sources(
    max_chars,
    expected_second_content,
):
    results = make_search_results("abc", "xyz")

    context = build_retrieval_context(
        results,
        max_chars=max_chars,
    )

    assert context.text == (
        "[Source 1]\nabc\n\n"
        f"[Source 2]\n{expected_second_content}"
    )

    assert len(context.text) == max_chars
    assert len(context.sources) == 2
    assert context.sources[1].content == expected_second_content


def test_context_budget_trims_whitespace_consistently():
    results = make_search_results("  PostgreSQL  \n")

    context = build_retrieval_context(results)

    assert context.text == "[Source 1]\nPostgreSQL"
    assert context.sources[0].content == "PostgreSQL"


@pytest.mark.parametrize(
    ("max_chars", "error_type", "message"),
    [
        (0, ValueError, "greater than zero"),
        (-5, ValueError, "greater than zero"),
        (True, TypeError, "must be an integer"),
        (1.5, TypeError, "must be an integer"),
    ],
)
def test_context_budget_validates_inputs_even_without_results(
    max_chars,
    error_type,
    message,
):
    with pytest.raises(error_type, match=message):
        build_retrieval_context(
            [],
            max_chars=max_chars,
        )
