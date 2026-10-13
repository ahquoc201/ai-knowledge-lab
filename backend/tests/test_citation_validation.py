
from uuid import uuid4

from app.services.citation_validation import validate_answer_citations
from app.services.context_builder import ContextSource


def make_sources(*indices: int) -> list[ContextSource]:
    return [
        ContextSource(
            source_index=index,
            document_id=uuid4(),
            chunk_id=uuid4(),
            chunk_index=index - 1,
            content=f"Knowledge from source {index}.",
            similarity=0.9,
        )
        for index in indices
    ]


def test_citation_validation_accepts_existing_sources():
    result = validate_answer_citations(
        "PostgreSQL [Source 1]. Redis [Source 2].",
        make_sources(1, 2),
    )

    assert result.is_valid is True
    assert result.cited_indices == (1, 2)
    assert result.invalid_citations == ()


def test_citation_validation_rejects_unknown_source():
    result = validate_answer_citations(
        "PostgreSQL [Source 1]. Redis [Source 9].",
        make_sources(1, 2),
    )

    assert result.is_valid is False
    assert result.cited_indices == (1,)
    assert result.invalid_citations == ("9",)


def test_citation_validation_rejects_missing_citations():
    result = validate_answer_citations(
        "PostgreSQL supports transactions.",
        make_sources(1),
    )

    assert result.is_valid is False
    assert result.cited_indices == ()
    assert result.invalid_citations == ()


def test_citation_validation_rejects_malformed_source():
    result = validate_answer_citations(
        "PostgreSQL [Source abc].",
        make_sources(1),
    )

    assert result.is_valid is False
    assert result.invalid_citations == ("abc",)


def test_citation_validation_checks_actual_source_indices():
    result = validate_answer_citations(
        "PostgreSQL [Source 1].",
        make_sources(2, 4),
    )

    assert result.is_valid is False
    assert result.invalid_citations == ("1",)


def test_citation_validation_deduplicates_references():
    result = validate_answer_citations(
        "PostgreSQL [Source 1]. ACID [Source 1].",
        make_sources(1),
    )

    assert result.is_valid is True
    assert result.cited_indices == (1,)


def test_citation_validation_rejects_lowercase_unknown_source():
    result = validate_answer_citations(
        "PostgreSQL [Source 1]. Redis [source 9].",
        make_sources(1),
    )

    assert result.is_valid is False
    assert result.cited_indices == (1,)
    assert result.invalid_citations == ("9",)


def test_citation_validation_requires_canonical_marker_case():
    result = validate_answer_citations(
        "PostgreSQL [Source 1]. Redis [SOURCE 2].",
        make_sources(1, 2),
    )

    assert result.is_valid is False
    assert result.cited_indices == (1,)
    assert result.invalid_citations == ("2",)


def test_citation_validation_handles_extremely_long_index():
    long_index = "9" * 5000

    result = validate_answer_citations(
        f"PostgreSQL [Source 1]. Redis [Source {long_index}].",
        make_sources(1),
    )

    assert result.is_valid is False
    assert result.cited_indices == (1,)
    assert result.invalid_citations == (long_index,)


def test_citation_validation_ignores_unrelated_brackets():
    result = validate_answer_citations(
        "PostgreSQL [Source 1]. Additional details [Note].",
        make_sources(1),
    )

    assert result.is_valid is True
    assert result.cited_indices == (1,)
    assert result.invalid_citations == ()


import pytest


@pytest.mark.parametrize(
    "malformed_citation",
    [
        "[Source: 9]",
        "[Source-9]",
        "[ Source 9]",
    ],
)
def test_citation_validation_rejects_malformed_reference(
    malformed_citation,
):
    answer = (
        "PostgreSQL supports ACID [Source 1]. "
        f"Redis supports caching {malformed_citation}."
    )

    result = validate_answer_citations(
        answer,
        make_sources(1),
    )

    assert result.is_valid is False
    assert result.cited_indices == (1,)
    assert result.invalid_citations == ("9",)


def test_citation_validation_rejects_unclosed_source_marker():
    """An incomplete source marker must not bypass validation."""
    result = validate_answer_citations(
        (
            "PostgreSQL supports ACID [Source 1]. "
            "Redis supports caching [Source 9"
        ),
        make_sources(1),
    )
    assert result.is_valid is False
    assert result.cited_indices == (1,)
    assert result.invalid_citations == ("9",)
