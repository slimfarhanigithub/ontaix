"""Process configuration bound from environment variables prefixed ONTAIX_."""

from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_ENVIRONMENT = "dev"

Environment = Literal["dev", "test", "staging", "production"]

MAX_LLM_TIMEOUT_SECONDS = 15.0
MAX_LLM_SPEECH_TIMEOUT_SECONDS = 45.0

LlmProvider = Literal["azure_foundry", "anthropic"]
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high"]
# What `python -m app.seed` loads into the demo tenant: only its directory, or the directory
# with the Northwind and Aurora example companies.
SeedMode = Literal["empty", "fixture"]


class ModelPrice(BaseModel):
    """Estimated euros per million input and output tokens of one model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_eur_per_mtok: Decimal = Field(alias="inputEurPerMTok", ge=0)
    output_eur_per_mtok: Decimal = Field(alias="outputEurPerMTok", ge=0)


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
    seed: SeedMode = "fixture"
    import_purge_interval_seconds: float = Field(default=15 * 60, gt=0)
    extraction_concurrency: int | None = Field(default=None, ge=1)
    extraction_memory_limit_bytes: int = Field(default=512 * 1024 * 1024, ge=0)
    llm_provider: LlmProvider = "azure_foundry"
    # Recorded in `llm_call.model` and looked up in the price table; with `anthropic`, also the
    # model id sent to the API.
    llm_model: str = Field(
        default="gpt-6-sol",
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
    # The Azure AI Foundry resource endpoint, for example https://<resource>.cognitiveservices.azure.com.
    # Authentication is Entra ID only (workload identity in the cluster, `az login` locally);
    # no key setting exists for this provider. Unset, the model step is `not_configured`.
    foundry_endpoint: str | None = Field(default=None, pattern=r"^https://[^\s/?#]+/?$")
    foundry_deployment: str = Field(
        default="gpt-6-sol",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    )
    # Reasoning tokens share the output bound with the answer; extraction asks for none.
    foundry_reasoning_effort: ReasoningEffort = "none"
    # Output tokens added to the answer bound for a model that reasons anyway; the reservation
    # and the provider's maximum output tokens both include it.
    llm_reasoning_allowance_tokens: int = Field(default=0, ge=0, le=16_384)
    # JSON: {"<model>": {"inputEurPerMTok": <number>, "outputEurPerMTok": <number>}}.
    llm_price_table: dict[str, ModelPrice] = Field(default_factory=dict)
    retention_purge_interval_seconds: float = Field(default=15 * 60, gt=0)

    @field_validator("foundry_endpoint", mode="before")
    @classmethod
    def _empty_endpoint_is_unset(cls, value: object) -> object:
        return None if value == "" else value

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
