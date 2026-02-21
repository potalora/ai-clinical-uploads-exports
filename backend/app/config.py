from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/../..


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Fail fast if production is running with insecure defaults."""
        if self.app_env != "development":
            if self.jwt_secret_key == "change-me-in-production":
                raise ValueError(
                    "JWT_SECRET_KEY must be changed from default in non-development environments"
                )
            if not self.database_encryption_key:
                raise ValueError(
                    "DATABASE_ENCRYPTION_KEY must be set in non-development environments"
                )
        return self

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
    gemini_concurrency_limit: int = 10

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
