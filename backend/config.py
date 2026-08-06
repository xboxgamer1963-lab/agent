from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    gemini_api_key: str
    tavily_api_key: str
    firecrawl_api_key: str
    pipedrive_api_key: str | None = None
    google_sheet_id: str
    google_service_account_json: str
    batch_size: int = 5
    relevance_threshold: int = 7
    nvidia_api_key: str | None = None
    ollama_model: str | None = None
    ollama_url: str = "http://localhost:11434/v1/chat/completions"
    # Auth
    secret_key: str = "change-me-in-env-please-use-a-long-random-string"
    app_email: str = "admin@insightengine.ai"
    app_password: str = "changeme"
    # Supabase — names match the keys already present in .env
    supabase_url: str = Field(alias="NEXT_PUBLIC_SUPABASE_URL")
    supabase_service_role_key: str = Field(alias="service_role_key")

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


settings = Settings()
