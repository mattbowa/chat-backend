import uuid
from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: uuid.UUID
    message: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    sources: list | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    session_id: uuid.UUID
    message_count: int
    last_message_at: datetime
