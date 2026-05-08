from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration is loaded strictly from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── OpenRouter ────────────────────────────────────────────────────────────
    openrouter_api_key: str
    openrouter_model: str = "meta-llama/llama-3.1-8b-instruct:free"
    openrouter_fallback_model: str = "mistralai/mistral-7b-instruct:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── Postgres ──────────────────────────────────────────────────────────────
    postgres_user: str = "megaai"
    postgres_password: str = "megaai"
    postgres_db: str = "megaai"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"

    # ── App behaviour ─────────────────────────────────────────────────────────
    max_context_tokens: int = 4000
    log_level: str = "INFO"

    # ── Derived ───────────────────────────────────────────────────────────────
    @property
    def database_url(self) -> str:
        """Sync DSN (used by Alembic offline mode)."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """Async DSN for SQLAlchemy asyncpg driver."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def openrouter_client(self):
        """Return a configured AsyncOpenAI client pointed at OpenRouter."""
        from openai import AsyncOpenAI  # local import to keep config light

        return AsyncOpenAI(
            base_url=self.openrouter_base_url,
            api_key=self.openrouter_api_key,
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — call this everywhere."""
    return Settings()


# Module-level convenience alias
settings: Settings = get_settings()
