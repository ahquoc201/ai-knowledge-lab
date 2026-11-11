from uuid import UUID

from pydantic import BaseModel, Field


class SemanticSearchRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=1000,
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
    )


class SemanticSearchResultResponse(BaseModel):
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    content: str
    similarity: float


class HybridSearchRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=1000,
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
    )
    workspace_id: UUID | None = None
    rrf_k: int = Field(
        default=60,
        ge=1,
        le=500,
    )


class HybridSearchResultResponse(BaseModel):
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    content: str
    rrf_score: float
    dense_rank: int | None = None
    keyword_rank: int | None = None
    dense_similarity: float | None = None
    keyword_score: float | None = None
    provenance: str
    document_title: str | None = None
