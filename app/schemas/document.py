import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    chunk_count: int
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
