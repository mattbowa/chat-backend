from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    supabase_url: str
    supabase_service_key: str
    supabase_storage_bucket: str = "documents"

    openai_api_key: str
    anthropic_api_key: str

    environment: str = "development"


settings = Settings()
