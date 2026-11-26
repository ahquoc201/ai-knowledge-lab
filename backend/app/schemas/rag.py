from uuid import UUID

from pydantic import BaseModel, Field


class RAGRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=2000,
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
    )
    conversation_id: UUID | None = None
    retrieval_mode: str = Field(
        default="dense",
        description="Retrieval mode: dense, keyword, or hybrid",
    )
    enable_reranking: bool = Field(
        default=False,
        description="Explicitly opt-in to Cross-Encoder reranking if enabled server-side.",
    )


class RAGSourceResponse(BaseModel):
    source_index: int
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    content: str
    similarity: float
    document_title: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    rerank_score: float | None = Field(
        default=None,
        description="Cross-Encoder reranking score if reranking was applied.",
    )


class RAGResponse(BaseModel):
    conversation_id: UUID
    answer: str
    sources: list[RAGSourceResponse]
    # Model that generated the answer (None when no generation was needed).
    model_name: str | None = None
    grounding_status: str | None = Field(
        default=None,
        description="Deterministic citation grounding status: verified, unsupported, or inconclusive.",
    )