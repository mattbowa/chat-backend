import uuid
from datetime import datetime

from pydantic import BaseModel


class IntegrationOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    last_synced_at: datetime | None
    error_message: str | None
    created_at: datetime
    site_url: str | None
    connected: bool


class WebsiteUpsert(BaseModel):
    site_url: str
