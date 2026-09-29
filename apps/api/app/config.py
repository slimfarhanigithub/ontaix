"""Process configuration bound from environment variables prefixed ONTAIX_."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_ENVIRONMENT = "dev"

Environment = Literal["dev", "test", "staging", "production"]

MAX_LLM_TIMEOUT_SECONDS = 15.0
MAX_LLM_SPEECH_TIMEOUT_SECONDS = 45.0


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
    extraction_concurrency: int | None = Field(default=None, ge=1)
    extraction_memory_limit_bytes: int = Field(default=512 * 1024 * 1024, ge=0)
    llm_provider: str = Field(default="anthropic", pattern=r"^[a-z0-9][a-z0-9_.-]{0,59}$")
    llm_model: str = Field(
        default="claude-sonnet-5",
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/@-]*$",
    )
    # Wall clock of one model call, connect included; above 15 or at most 0 stops start-up.
    llm_timeout_seconds: float = Field(
        default=MAX_LLM_TIMEOUT_SECONDS, gt=0, le=MAX_LLM_TIMEOUT_SECONDS
    )
    # The same for a whole speech transcript; above 45 or at most 0 stops start-up.
    llm_speech_timeout_seconds: float = Field(
        default=MAX_LLM_SPEECH_TIMEOUT_SECONDS, gt=0, le=MAX_LLM_SPEECH_TIMEOUT_SECONDS
    )
    llm_calls_per_hour: int = Field(default=200, ge=0)
    # Read from ONTAIX_ANTHROPIC_API_KEY; never logged, never returned, never stored.
    anthropic_api_key: SecretStr | None = Field(default=None, repr=False)
    retention_purge_interval_seconds: float = Field(default=15 * 60, gt=0)

    def extraction_slots(self) -> int:
        """Extractions one process runs at once: configured, else half the CPUs, at least 2."""
        return self.extraction_concurrency or max(2, (os.cpu_count() or 1) // 2)

    @property
    def is_dev(self) -> bool:
        """True only when the environment is exactly `dev`: the dev identity header is accepted."""
        return self.environment == DEV_ENVIRONMENT


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance, built once on first use."""
    return Settings()
