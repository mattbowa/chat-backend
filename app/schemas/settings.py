from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    system_prompt: str
    model: str
    temperature: float
    top_k_chunks: int
    max_response_tokens: int
    fallback_message: str
    suggested_questions: list[str]
    bot_name: str
    primary_color: str
    logo_url: str | None

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=1.0)
    top_k_chunks: int | None = Field(None, ge=1, le=20)
    max_response_tokens: int | None = Field(None, ge=256, le=4096)
    fallback_message: str | None = None
    suggested_questions: list[str] | None = None
    bot_name: str | None = None
    primary_color: str | None = None
    logo_url: str | None = None
