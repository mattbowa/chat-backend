import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    message: str = Field(min_length=1, max_length=5000)
    source: str = Field(default="contact_page", max_length=50)


class ContactOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    name: str
    email: str
    message: str
    source: str
    handled: bool
    created_at: datetime

    model_config = {"from_attributes": True}
