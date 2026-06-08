from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    gemini_api_key: str
    tavily_api_key: str
    firecrawl_api_key: str
    pipedrive_api_key: str
    google_sheet_id: str
    google_service_account_json: str
    batch_size: int = 5
    relevance_threshold: int = 7
    nvidia_api_key: str | None = None
    ollama_model: str | None = None
    ollama_url: str = "http://localhost:11434/v1/chat/completions"

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
