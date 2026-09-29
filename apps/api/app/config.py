"""Process configuration bound from environment variables prefixed ONTAIX_."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_ENVIRONMENT = "dev"

Environment = Literal["dev", "test", "staging", "production"]


class Settings(BaseSettings):
    """Runtime settings for the API process.

    Every field is read from the environment as ONTAIX_<FIELD>, for example
    ONTAIX_DATABASE_URL. Values are never logged.

    `environment` fails closed: it defaults to `production`, and a value outside the known
    environments stops the process at startup instead of silently enabling anything.
    """

    model_config = SettingsConfigDict(env_prefix="ONTAIX_", env_file=".env", extra="ignore")

    app_name: str = "ontaix-api"
    environment: Environment = Field(
        default="production",
        validation_alias=AliasChoices("ONTAIX_ENVIRONMENT", "ONTAIX_ENV"),
    )
    log_level: str = "INFO"
    database_url: str | None = None
    test_seed: int | None = None
    import_purge_interval_seconds: float = Field(default=15 * 60, gt=0)

    @property
    def is_dev(self) -> bool:
        """True only when the environment is exactly `dev`: the dev identity header is accepted."""
        return self.environment == DEV_ENVIRONMENT


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance, built once on first use."""
    return Settings()
