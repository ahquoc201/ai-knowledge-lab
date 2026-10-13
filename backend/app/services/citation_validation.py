
"""Validate source references in RAG-generated answers."""

import re
from dataclasses import dataclass

from app.services.context_builder import ContextSource

_SOURCE_CITATION_PATTERN = re.compile(
    r"\[(\s*)(Source)([\s:-]*)([^\]\r\n]*)(\]|$)",
    flags=re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class CitationValidationResult:
    is_valid: bool
    cited_indices: tuple[int, ...]
    invalid_citations: tuple[str, ...]


def validate_answer_citations(
    answer: str,
    sources: list[ContextSource],
) -> CitationValidationResult:
    """Validate citations against available retrieved sources.

    Only canonical [Source N] markers are accepted.
    Avoid converting arbitrary LLM-generated numbers to int.
    """

    available_indices = {
        str(source.source_index): source.source_index
        for source in sources
    }

    cited_indices: list[int] = []
    invalid_citations: list[str] = []

    for match in _SOURCE_CITATION_PATTERN.finditer(answer):
        leading_space, marker_name, separator, value, closing_bracket = (
            match.groups()
        )

        raw_index = value.strip()

        is_canonical = (
            closing_bracket == "]"
            and not leading_space
            and marker_name == "Source"
            and separator == " "
            and value == raw_index
        )

        is_valid_number = (
            re.fullmatch(r"[1-9][0-9]*", raw_index)
            is not None
        )

        if not is_canonical or not is_valid_number:
            if raw_index not in invalid_citations:
                invalid_citations.append(raw_index)
            continue

        source_index = available_indices.get(raw_index)

        if source_index is None:
            if raw_index not in invalid_citations:
                invalid_citations.append(raw_index)
            continue

        if source_index not in cited_indices:
            cited_indices.append(source_index)

    return CitationValidationResult(
        is_valid=(
            bool(cited_indices)
            and not invalid_citations
        ),
        cited_indices=tuple(cited_indices),
        invalid_citations=tuple(invalid_citations),
    )