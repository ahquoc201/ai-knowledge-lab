from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentChunkCreateRequest(BaseModel):
    chunk_size: int = Field(
        default=1000,
        gt=0,
    )
    overlap: int = Field(
        default=200,
        ge=0,
    )

    @model_validator(mode="after")
    def validate_overlap(self) -> Self:
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        return self


class DocumentChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    created_at: datetime