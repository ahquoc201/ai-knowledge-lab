from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MessageSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_index: int
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    content: str
    similarity: float
    document_title: str | None = None
    char_start: int | None = None
    char_end: int | None = None