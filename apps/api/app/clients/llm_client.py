"""Provider-neutral language model adapter: one request in, JSON text and token counts out.

The rest of the API sees only this module. A request carries the system instructions, one user
message and the JSON schema the answer must follow; the answer carries the raw JSON text, token
counts, the estimated euro cost and the latency. A timeout or a provider failure raises
`LlmTimeout` or `LlmProviderError` (`LlmRefused` for a content filter or a declining model),
each with the tokens the provider reported (0 when none).
No provider type, SDK class or credential leaves the implementation modules.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from app.config import ModelPrice, ReasoningEffort, Settings, get_settings

logger = logging.getLogger(__name__)

# The input estimate is the larger of code points / 2 (Latin scripts) and UTF-8 bytes / 3
# (scripts where one character is a token or more), so a reservation errs on counting too much.
CODE_POINTS_PER_TOKEN = 2
BYTES_PER_TOKEN = 3
# `llm_call.latency_ms` holds at most five minutes.
MAX_LATENCY_MS = 300_000


class LlmPurpose(StrEnum):
    """Why Ontaix calls a model; each purpose has its own deployment, model and effort."""

    TEACH_EXTRACTION = "teach_extraction"
    CONCEPT_EXPANSION = "concept_expansion"
    DOCUMENT_EXTRACTION = "document_extraction"


@dataclass(frozen=True)
class LlmProfile:
    """The deployment (Azure AI Foundry), model name and reasoning effort of one purpose."""

    deployment: str
    model: str
    reasoning_effort: ReasoningEffort


@dataclass(frozen=True)
class LlmRequest:
    system: str
    user: str
    output_schema: dict[str, Any]
    max_output_tokens: int
    # Wall clock of the whole call, DNS, connect and TLS included.
    timeout_seconds: float


@dataclass(frozen=True)
class LlmAnswer:
    text: str
    input_tokens: int
    output_tokens: int
    cost_eur: float
    latency_ms: int


class LlmCallError(Exception):
    """A call that produced no usable answer; carries what the provider reported."""

    def __init__(
        self,
        reason: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_eur: float = 0.0,
        latency_ms: int = 0,
    ) -> None:
        super().__init__(reason)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_eur = cost_eur
        self.latency_ms = latency_ms


class LlmTimeout(LlmCallError):
    """No complete answer within the wall-clock timeout."""


class LlmProviderError(LlmCallError):
    """The provider refused, failed, rate-limited, or stopped before a complete answer."""


class LlmRefused(LlmProviderError):
    """The provider's content filter blocked the request or the answer, or the model declined."""


class LlmConfigurationError(RuntimeError):
    """The configured provider cannot run: raised at start-up, never during a request."""


class LlmClient(Protocol):
    provider: str
    model: str

    def estimate_input_tokens(self, request: LlmRequest) -> int: ...

    async def complete(self, request: LlmRequest) -> LlmAnswer: ...


_override: LlmClient | None = None
_override_set = False
_cached: dict[LlmPurpose, tuple[tuple[object, ...], LlmClient]] = {}


def get_llm_client(purpose: LlmPurpose = LlmPurpose.TEACH_EXTRACTION) -> LlmClient | None:
    """The client configured for `purpose`, or None when the provider has no endpoint, key or
    price for its model."""
    if _override_set:
        return _override
    return _configured(get_settings(), purpose)


def set_llm_client(client: LlmClient | None) -> None:
    """Replace the configured client of every purpose (tests); `reset_llm_client` restores
    configuration."""
    global _override, _override_set
    _override, _override_set = client, True


def reset_llm_client() -> None:
    global _override, _override_set
    _override, _override_set = None, False


def check_llm_configuration(settings: Settings) -> None:
    """Stops start-up when a provider is configured but the model of a purpose has no price.

    A provider without its endpoint (`azure_foundry`) or key (`anthropic`) is not an error: the
    model step answers `not_configured` and the grammar runs alone.
    """
    if not _provider_configured(settings):
        return
    variables = {
        LlmPurpose.TEACH_EXTRACTION: "ONTAIX_LLM_MODEL",
        LlmPurpose.CONCEPT_EXPANSION: "ONTAIX_EXPAND_MODEL",
        LlmPurpose.DOCUMENT_EXTRACTION: "ONTAIX_DOCUMENT_EXTRACTION_MODEL",
    }
    for purpose, variable in variables.items():
        model = profile_for(settings, purpose).model
        if model not in settings.llm_price_table:
            raise LlmConfigurationError(
                f"ONTAIX_LLM_PRICE_TABLE has no price for {variable} {model!r}"
            )


def profile_for(settings: Settings, purpose: LlmPurpose) -> LlmProfile:
    """The deployment, model and effort of a purpose; unset ones fall back to the teach ones."""
    if purpose is LlmPurpose.CONCEPT_EXPANSION:
        return LlmProfile(
            settings.expand_deployment or settings.foundry_deployment,
            settings.expand_model or settings.llm_model,
            settings.expand_reasoning_effort,
        )
    if purpose is LlmPurpose.DOCUMENT_EXTRACTION:
        return LlmProfile(
            settings.document_extraction_deployment or settings.foundry_deployment,
            settings.document_extraction_model or settings.llm_model,
            settings.document_extraction_reasoning_effort,
        )
    return LlmProfile(
        settings.foundry_deployment, settings.llm_model, settings.foundry_reasoning_effort
    )


def estimate_tokens(request: LlmRequest) -> int:
    """A provider-independent upper estimate of the request's input tokens."""
    assembled = request.system + request.user + json.dumps(request.output_schema)
    by_code_points = -(-len(assembled) // CODE_POINTS_PER_TOKEN)
    by_bytes = -(-len(assembled.encode("utf-8")) // BYTES_PER_TOKEN)
    return max(by_code_points, by_bytes)


def cost_eur(price: ModelPrice, input_tokens: int, output_tokens: int) -> float:
    """Estimated euros of a call: tokens times the price per million, rounded to 6 places."""
    cost = (
        price.input_eur_per_mtok * input_tokens + price.output_eur_per_mtok * output_tokens
    ) / Decimal(1_000_000)
    return float(round(cost, 6))


def elapsed_ms(started: float) -> int:
    """Milliseconds since `started` (a `time.monotonic()` value), capped at five minutes."""
    return min(MAX_LATENCY_MS, max(0, int((time.monotonic() - started) * 1000)))


def _provider_configured(settings: Settings) -> bool:
    if settings.llm_provider == "azure_foundry":
        return settings.foundry_endpoint is not None
    key = settings.anthropic_api_key
    return key is not None and bool(key.get_secret_value())


def _configured(
    settings: Settings, purpose: LlmPurpose = LlmPurpose.TEACH_EXTRACTION
) -> LlmClient | None:
    profile = profile_for(settings, purpose)
    price = settings.llm_price_table.get(profile.model)
    if not _provider_configured(settings) or price is None:
        return None
    if settings.llm_provider == "azure_foundry":
        fingerprint: tuple[object, ...] = (
            settings.llm_provider,
            profile,
            price,
            settings.foundry_endpoint,
        )
    else:
        key = settings.anthropic_api_key.get_secret_value()  # type: ignore[union-attr]
        fingerprint = (
            settings.llm_provider,
            profile.model,
            price,
            hashlib.sha256(key.encode()).hexdigest(),
        )
    cached = _cached.get(purpose)
    if cached is None or cached[0] != fingerprint:
        cached = (fingerprint, _build(settings, profile, price))
        _cached[purpose] = cached
    return cached[1]


def _build(settings: Settings, profile: LlmProfile, price: ModelPrice) -> LlmClient:
    if settings.llm_provider == "azure_foundry":
        from app.clients.foundry_llm_client import FoundryLlmClient

        return FoundryLlmClient(
            endpoint=settings.foundry_endpoint or "",
            deployment=profile.deployment,
            model=profile.model,
            price=price,
            reasoning_effort=profile.reasoning_effort,
        )
    from app.clients.anthropic_llm_client import AnthropicLlmClient

    key = settings.anthropic_api_key.get_secret_value()  # type: ignore[union-attr]
    return AnthropicLlmClient(key, profile.model, price)
