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