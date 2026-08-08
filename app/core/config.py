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

    # Contact form notifications. Unset resend_api_key disables sending —
    # submissions are still persisted to contact_submissions.
    resend_api_key: str = ""
    contact_from_email: str = "onboarding@resend.dev"
    contact_to_email: str = "matt.bowa04@gmail.com"

    monthly_message_limit: int = 100

    environment: str = "development"


settings = Settings()
