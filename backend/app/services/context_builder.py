from dataclasses import dataclass
from uuid import UUID

from app.services.semantic_search import SemanticSearchResult


@dataclass(frozen=True, slots=True)
class ContextSource:
    source_index: int
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    content: str
    similarity: float


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    text: str
    sources: list[ContextSource]


def build_retrieval_context(
    results: list[SemanticSearchResult],
) -> RetrievalContext:
    sources: list[ContextSource] = []
    context_blocks: list[str] = []

    for source_index, result in enumerate(results, start=1):
        source = ContextSource(
            source_index=source_index,
            document_id=result.chunk.document_id,
            chunk_id=result.chunk.id,
            chunk_index=result.chunk.chunk_index,
            content=result.chunk.content,
            similarity=result.similarity,
        )

        sources.append(source)

        context_blocks.append(
            f"[Source {source_index}]\n"
            f"{result.chunk.content.strip()}"
        )

    return RetrievalContext(
        text="\n\n".join(context_blocks),
        sources=sources,
    )