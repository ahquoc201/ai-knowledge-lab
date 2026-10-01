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


class RAGSourceResponse(BaseModel):
    source_index: int
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    content: str
    similarity: float


class RAGResponse(BaseModel):
    answer: str
    sources: list[RAGSourceResponse]