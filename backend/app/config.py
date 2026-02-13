from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://localhost:5432/medtimeline"
    database_encryption_key: str = ""

    # Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # AI Prompt Builder
    prompt_target_model: str = "gemini-3-flash-preview"
    prompt_suggested_temperature: float = 0.3
    prompt_suggested_max_tokens: int = 4096
    prompt_suggested_thinking_level: str = "low"

    # Gemini API
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3-flash-preview"
    gemini_extraction_model: str = "gemini-2.5-flash"
    gemini_summary_temperature: float = 0.3
    gemini_summary_max_tokens: int = 8192

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # File Storage
    upload_dir: str = "./data/uploads"
    temp_extract_dir: str = "./data/tmp"
    max_file_size_mb: int = 500
    max_epic_export_size_mb: int = 5000
    ingestion_batch_size: int = 100
    ingestion_worker_concurrency: int = 1

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"


settings = Settings()
