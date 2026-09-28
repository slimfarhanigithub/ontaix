"""Process configuration bound from environment variables prefixed ONTAIX_."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the gateway process.

    Every field is read from the environment as ONTAIX_<FIELD>, for example
    ONTAIX_API_BASE_URL. Values are never logged.
    """

    model_config = SettingsConfigDict(env_prefix="ONTAIX_", env_file=".env", extra="ignore")

    app_name: str = "ontaix-gateway"
    environment: str = "dev"
    log_level: str = "INFO"
    api_base_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance, built once on first use."""
    return Settings()
