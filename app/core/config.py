"""Application settings, loaded once from the environment.

Every value here comes from an env var (see `.env.example`). App code reads
settings through `get_settings()`, never `os.environ` directly, so there is a
single typed, validated place where configuration enters the system.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TORTOISEANDHIRE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Deployment platforms (Neon, Render, ...) inject a bare `DATABASE_URL`, so
    # this one field opts out of the TORTOISEANDHIRE_ prefix.
    database_url: str = Field(
        default="postgresql+psycopg://tortoiseandhire:tortoiseandhire@localhost:5432/tortoiseandhire",
        validation_alias="DATABASE_URL",
    )

    api_token: str = "change-me"
    env: Environment = "development"
    log_level: str = "INFO"
    timezone: str = "America/New_York"
    discovery_ruleset_path: str = "config/discovery.yml"
    metrics_enabled: bool = True

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """The process-wide Settings instance. Cached so the environment is read once."""
    return Settings()
