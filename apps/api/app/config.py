"""Process configuration bound from environment variables prefixed ONTAIX_."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API process.

    Every field is read from the environment as ONTAIX_<FIELD>, for example
    ONTAIX_DATABASE_URL. Values are never logged.
    """

    model_config = SettingsConfigDict(env_prefix="ONTAIX_", env_file=".env", extra="ignore")

    app_name: str = "ontaix-api"
    environment: str = Field(
        default="dev",
        validation_alias=AliasChoices("ONTAIX_ENVIRONMENT", "ONTAIX_ENV"),
    )
    log_level: str = "INFO"
    database_url: str | None = None
    test_seed: int | None = None

    @property
    def is_dev(self) -> bool:
        """True when the dev identity header is accepted in place of an OIDC token."""
        return self.environment == "dev"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance, built once on first use."""
    return Settings()
