import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.qa import MAX_ANSWER_LEN, MAX_QUESTION_LEN


class QAPairCreate(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LEN)
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_LEN)


class QAPairUpdate(QAPairCreate):
    pass


class QAPairOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question: str
    answer: str
    created_at: datetime
    updated_at: datetime
