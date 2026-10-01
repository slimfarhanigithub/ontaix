"""Process configuration bound from environment variables prefixed ONTAIX_."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "staging", "production"]
# The only environments where the development identity header may be switched on.
DEV_IDENTITY_ENVIRONMENTS: tuple[Environment, ...] = ("dev", "test")

MAX_LLM_TIMEOUT_SECONDS = 15.0
MAX_LLM_SPEECH_TIMEOUT_SECONDS = 45.0
# Concept expansion and whole-document extraction calls; `llm_call.latency_ms` holds at most 300 s.
MAX_LONG_CALL_TIMEOUT_SECONDS = 300.0
DEFAULT_EXPAND_TIMEOUT_SECONDS = 120.0
DEFAULT_DOCUMENT_EXTRACTION_TIMEOUT_SECONDS = 180.0
MAX_OCR_TIMEOUT_SECONDS = 300.0
MAX_ONTOLOGY_IMPORT_NODES = 20_000

LlmProvider = Literal["azure_foundry", "anthropic", "anthropic_foundry"]
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high"]
# Model calls run on one of two profiles: `live` for typed text and speech, where latency
# matters, and `deep` for document sentences, concept expansion and whole-document extraction.
LlmProfile = Literal["live", "deep"]
LLM_PROFILES: tuple[LlmProfile, ...] = ("live", "deep")
# What `python -m app.seed` loads into the demo tenant: only its directory, or the directory
# with the Northwind and Aurora example companies.
SeedMode = Literal["empty", "fixture"]
# Speech recognition is English only; the Studio passes the language to the Speech SDK.
SpeechLanguage = Literal["en-GB", "en-US"]
SpeechRegion = Literal["francecentral"]


class ModelPrice(BaseModel):
    """Estimated euros per million input and output tokens of one model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_eur_per_mtok: Decimal = Field(alias="inputEurPerMTok", ge=0)
    output_eur_per_mtok: Decimal = Field(alias="outputEurPerMTok", ge=0)


class PagePrice(BaseModel):
    """Estimated euros per page of a model priced by the page (OCR)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    eur_per_page: Decimal = Field(alias="eurPerPage", ge=0)


@dataclass(frozen=True)
class LlmProfileSettings:
    """The deployment, reasoning effort and reasoning allowance one model profile runs with."""

    deployment: str
    reasoning_effort: ReasoningEffort
    reasoning_allowance_tokens: int


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
    # Organization requests and per-organization jobs connect here as the database role
    # `ontaix_app`, which row-level security confines to one organization per transaction.
    database_url: str | None = None
    # Sign-in, the platform portal and cross-organization jobs connect here as the database role
    # `ontaix_platform`; unset, the same login as `database_url` switches to that role.
    platform_database_url: str | None = None
    # The login name inside `database_url`, for `python -m app.admin grant-database-roles`, which
    # grants it `ontaix_app`. A login name, never a secret; unset, the command grants nothing.
    app_database_login: str | None = None
    # The login name inside `platform_database_url`, granted `ontaix_platform` by the same
    # command; unset, `app_database_login` holds both roles.
    platform_database_login: str | None = None
    # `X-Ontaix-User: <email>` names a seeded `dev` user without a session. Accepted only when
    # this is true and `environment` is dev or test; true anywhere else stops start-up.
    dev_identity_header: bool = False
    # Origins allowed to send cookie-authenticated writes and sign-in (`Origin` header), as a
    # JSON list, for example ["https://studio.example"]. Empty refuses every such request.
    allowed_origins: list[str] = Field(default_factory=list)
    # Reverse proxies in front of the API whose `X-Forwarded-For` entry is trusted: 0 uses the
    # socket peer, 1 the entry the ingress appended, and so on.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    test_seed: int | None = None
    seed: SeedMode = "fixture"
    import_purge_interval_seconds: float = Field(default=15 * 60, gt=0)
    extraction_concurrency: int | None = Field(default=None, ge=1)
    extraction_memory_limit_bytes: int = Field(default=512 * 1024 * 1024, ge=0)
    llm_provider: LlmProvider = "azure_foundry"
    # With `anthropic`: the model id sent to the API, recorded in `llm_call.model` and looked up
    # in the price table. The Foundry providers record and price the deployment they call.
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
    # The Azure AI Foundry resource endpoint, for example https://<resource>.cognitiveservices.azure.com,
    # for `azure_foundry` and `anthropic_foundry` (Claude, whose deployment name is sent as the
    # model). Authentication is Entra ID only (workload identity in the cluster, `az login`
    # locally); no key setting exists for these providers. Unset, the model step is
    # `not_configured`.
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
    # The `deep` profile. The three settings above are the `live` profile; each deep setting
    # left unset takes its live value, so an unconfigured deep profile runs as live does.
    foundry_deep_deployment: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    )
    foundry_deep_reasoning_effort: ReasoningEffort | None = None
    llm_deep_reasoning_allowance_tokens: int | None = Field(default=None, ge=0, le=16_384)
    # JSON: {"<model>": {"inputEurPerMTok": <number>, "outputEurPerMTok": <number>}}, or
    # {"<model>": {"eurPerPage": <number>}} for a model priced by the page (OCR).
    llm_price_table: dict[str, ModelPrice | PagePrice] = Field(default_factory=dict)
    # OCR of image-only PDF pages. The endpoint defaults to `foundry_endpoint`; with neither, OCR
    # is not configured and a PDF that needs it is refused with `503`.
    ocr_endpoint: str | None = Field(default=None, pattern=r"^https://[^\s/?#]+/?$")
    ocr_deployment: str = Field(
        default="mistral-document-ai",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    )
    # Recorded in `llm_call.model` and looked up in the price table; defaults to the deployment.
    ocr_model: str | None = Field(
        default=None, min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/@-]*$"
    )
    ocr_max_pages: int = Field(default=100, ge=1, le=2000)
    ocr_timeout_seconds: float = Field(default=120.0, gt=0, le=MAX_OCR_TIMEOUT_SECONDS)
    ocr_pages_per_hour: int = Field(default=600, ge=0)
    ontology_import_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    ontology_import_max_nodes: int = Field(default=5000, ge=1, le=MAX_ONTOLOGY_IMPORT_NODES)
    ontology_import_parse_timeout_seconds: float = Field(default=60.0, gt=0)
    # Export (`GET /export`): the concept limit (`413` above), the hourly budget per caller, the
    # child-process time limit, and the base of every exported IRI.
    export_max_concepts: int = Field(default=20_000, ge=1)
    export_per_hour: int = Field(default=20, ge=0)
    export_timeout_seconds: float = Field(default=60.0, gt=0)
    export_base_iri: str = Field(
        default="urn:ontaix:",
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z][A-Za-z0-9+.-]*:\S*$",
    )
    retention_purge_interval_seconds: float = Field(default=15 * 60, gt=0)
    # The Azure AI Speech resource the microphone streams to: its full resource id, region and
    # endpoint (custom subdomain). Unset id or endpoint answers `POST /speech/token` with 503 and
    # the Studio uses the browser's recogniser.
    speech_resource_id: str | None = Field(
        default=None, max_length=512, pattern=r"^/subscriptions/[^#\s]+$"
    )
    speech_region: SpeechRegion = "francecentral"
    speech_endpoint: str | None = Field(default=None, pattern=r"^https://[^\s/?#]+/?$")
    # Client id of the dedicated managed identity whose Entra token the API exchanges at the
    # Speech resource's STS endpoint; it holds roles on the Speech resource only. Unset, the
    # developer's `az login` is used instead, only in `dev` and only without
    # AZURE_FEDERATED_TOKEN_FILE; otherwise the answer is 503. The browser only ever receives
    # the Speech STS token.
    speech_client_id: str | None = Field(
        default=None, pattern=r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$"
    )
    # Set by Kubernetes workload identity in a pod; its presence rules out the `az login`
    # fallback for speech tokens.
    azure_federated_token_file: str | None = Field(
        default=None, validation_alias="AZURE_FEDERATED_TOKEN_FILE"
    )
    speech_language: SpeechLanguage = "en-GB"
    speech_tokens_per_hour: int = Field(default=60, ge=0)

    # Concept expansion runs on the `deep` profile; these bound its cost and wait.
    expand_max_nodes: int = Field(default=200, ge=1, le=2000)
    expand_max_output_tokens: int = Field(default=32_768, ge=1, le=131_072)
    expand_context_labels: int = Field(default=1000, ge=0, le=100_000)
    expand_timeout_seconds: float = Field(
        default=DEFAULT_EXPAND_TIMEOUT_SECONDS, gt=0, le=MAX_LONG_CALL_TIMEOUT_SECONDS
    )
    expand_calls_per_hour: int = Field(default=30, ge=0)

    # Whole-document extraction runs on the `deep` profile; these bound its size, cost and wait.
    document_extraction_chunk_chars: int = Field(default=10_000, ge=500, le=100_000)
    document_extraction_outline_context_nodes: int = Field(default=600, ge=1, le=5000)
    document_extraction_max_nodes: int = Field(default=2000, ge=1, le=5000)
    document_extraction_max_tokens: int = Field(default=1_000_000, ge=1, le=2_000_000_000)
    document_extraction_max_chars: int = Field(default=400_000, ge=1, le=2_000_000)
    document_extraction_timeout_seconds: float = Field(
        default=DEFAULT_DOCUMENT_EXTRACTION_TIMEOUT_SECONDS,
        gt=0,
        le=MAX_LONG_CALL_TIMEOUT_SECONDS,
    )
    document_extraction_job_timeout_minutes: float = Field(default=60, gt=0)
    document_extraction_jobs_per_hour: int = Field(default=5, ge=0)
    document_extraction_max_attempts: int = Field(default=3, ge=1, le=10)
    # How often an idle runner looks for queued work.
    document_extraction_poll_seconds: float = Field(default=5, gt=0)
    branch_approve_batch: int = Field(default=200, ge=1, le=5000)
    branch_approve_max_rounds: int = Field(default=50, ge=1, le=10_000)

    # Usage learning: the deployment switch (false stops all capture and retrieval; the eval
    # harness sets it false), the token budget of lessons and negatives per model call, and how
    # long after a reject a re-teach outside the same session still links as a correction.
    learning_enabled: bool = True
    learning_context_tokens: int = Field(default=1500, ge=0, le=100_000)
    learning_correction_window_minutes: float = Field(default=10, ge=0, le=24 * 60)

    @field_validator(
        "foundry_endpoint",
        "speech_resource_id",
        "speech_endpoint",
        "speech_client_id",
        "azure_federated_token_file",
        "foundry_deep_deployment",
        "foundry_deep_reasoning_effort",
        "llm_deep_reasoning_allowance_tokens",
        "ocr_endpoint",
        "ocr_model",
        "platform_database_url",
        "app_database_login",
        "platform_database_login",
        mode="before",
    )
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    def ocr_endpoint_or_default(self) -> str | None:
        """The endpoint serving OCR: its own setting, else the Foundry endpoint."""
        return self.ocr_endpoint or self.foundry_endpoint

    def ocr_model_name(self) -> str:
        """The OCR model recorded in cost rows: its own setting, else the deployment."""
        return self.ocr_model or self.ocr_deployment

    def llm_profile(self, profile: LlmProfile) -> LlmProfileSettings:
        """The settings `profile` runs with; an unset deep setting takes its live value."""
        live = LlmProfileSettings(
            deployment=self.foundry_deployment,
            reasoning_effort=self.foundry_reasoning_effort,
            reasoning_allowance_tokens=self.llm_reasoning_allowance_tokens,
        )
        if profile == "live":
            return live
        return LlmProfileSettings(
            deployment=self.foundry_deep_deployment or live.deployment,
            reasoning_effort=self.foundry_deep_reasoning_effort or live.reasoning_effort,
            reasoning_allowance_tokens=(
                live.reasoning_allowance_tokens
                if self.llm_deep_reasoning_allowance_tokens is None
                else self.llm_deep_reasoning_allowance_tokens
            ),
        )

    def extraction_slots(self) -> int:
        """Extractions one process runs at once: configured, else half the CPUs, at least 2."""
        return self.extraction_concurrency or max(2, (os.cpu_count() or 1) // 2)

    @model_validator(mode="after")
    def _dev_identity_only_in_dev_or_test(self) -> Settings:
        if self.dev_identity_header and self.environment not in DEV_IDENTITY_ENVIRONMENTS:
            raise ValueError(
                "ONTAIX_DEV_IDENTITY_HEADER may be true only when ONTAIX_ENVIRONMENT is dev or test"
            )
        return self

    @property
    def accepts_dev_identity_header(self) -> bool:
        """True only in dev or test with ONTAIX_DEV_IDENTITY_HEADER on."""
        return self.dev_identity_header and self.environment in DEV_IDENTITY_ENVIRONMENTS

    @property
    def is_dev(self) -> bool:
        """True only when the environment is exactly `dev`: the Azure CLI may hand out tokens."""
        return self.environment == "dev"

    def platform_database_url_or_default(self) -> str | None:
        """The platform role's connection: its own setting, else `database_url`."""
        return self.platform_database_url or self.database_url

    def platform_database_login_or_default(self) -> str | None:
        """The login granted `ontaix_platform`: its own setting, else `app_database_login`."""
        return self.platform_database_login or self.app_database_login


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance, built once on first use."""
    return Settings()
