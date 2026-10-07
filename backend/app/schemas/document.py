from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str | None = None
    source_type: str = Field(default="text", max_length=50)
    source_name: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=100)

class DocumentUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    content: str | None = None

class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    source_type: str
    source_name: str | None
    mime_type: str | None
    content: str | None
    status: str
    created_at: datetime
    updated_at: datetime