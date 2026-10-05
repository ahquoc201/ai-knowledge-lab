from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.message_role import MessageRole


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    created_at: datetime