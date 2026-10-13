"""Build bounded retrieval context for RAG prompts."""

from dataclasses import dataclass
from uuid import UUID

from app.services.semantic_search import SemanticSearchResult

DEFAULT_CONTEXT_MAX_CHARS = 8000


@dataclass(frozen=True, slots=True)
class ContextSource:
    source_index: int
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    content: str
    similarity: float
    document_title: str | None = None
    char_start: int | None = None
    char_end: int | None = None


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    text: str
    sources: list[ContextSource]


def build_retrieval_context(
    results: list[SemanticSearchResult],
    *,
    max_chars: int = DEFAULT_CONTEXT_MAX_CHARS,
) -> RetrievalContext:
    """Build context within a strict character budget.

    Preserve retrieval ranking, keep source references aligned,
    and expose only the content actually included in the prompt.
    """

    if isinstance(max_chars, bool) or not isinstance(max_chars, int):
        raise TypeError("max_chars must be an integer")

    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")

    sources: list[ContextSource] = []
    context_blocks: list[str] = []
    used_chars = 0

    for result in results:
        content = result.chunk.content.strip()

        if not content:
            continue

        source_index = len(sources) + 1
        header = f"[Source {source_index}]\n"
        separator = "\n\n" if context_blocks else ""

        available_chars = (
            max_chars
            - used_chars
            - len(separator)
            - len(header)
        )

        # At least one content character must fit.
        if available_chars <= 0:
            break

        included_content = content[:available_chars]

        source = ContextSource(
            source_index=source_index,
            document_id=result.chunk.document_id,
            chunk_id=result.chunk.id,
            chunk_index=result.chunk.chunk_index,
            content=included_content,
            similarity=result.similarity,
            document_title=result.document_title,
            char_start=result.chunk.char_start,
            char_end=result.chunk.char_end,
        )

        sources.append(source)

        block = f"{header}{included_content}"
        context_blocks.append(block)

        used_chars += len(separator) + len(block)

        # The current source exhausted the remaining budget.
        # Do not include any lower-ranked sources.
        if len(included_content) < len(content):
            break

    return RetrievalContext(
        text="\n\n".join(context_blocks),
        sources=sources,
    )
