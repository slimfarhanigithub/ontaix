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
from typing import Any, Protocol

from app.config import (
    LLM_PROFILES,
    LlmProfile,
    LlmProfileSettings,
    ModelPrice,
    Settings,
    get_settings,
)

logger = logging.getLogger(__name__)

# The input estimate is the larger of code points / 2 (Latin scripts) and UTF-8 bytes / 3
# (scripts where one character is a token or more), so a reservation errs on counting too much.
CODE_POINTS_PER_TOKEN = 2
BYTES_PER_TOKEN = 3
# `llm_call.latency_ms` holds at most five minutes.
MAX_LATENCY_MS = 300_000
# Providers reached keylessly through the Azure AI Foundry endpoint settings.
FOUNDRY_PROVIDERS = ("azure_foundry", "anthropic_foundry")


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


# Clients installed per profile by tests; a profile without one is built from configuration.
_overrides: dict[LlmProfile, LlmClient | None] = {}
# One built client per profile, rebuilt when the settings it came from change.
_cached: dict[LlmProfile, tuple[tuple[object, ...], LlmClient]] = {}


def get_llm_client(profile: LlmProfile = "live") -> LlmClient | None:
    """The client of `profile`, or None when the provider has no endpoint, key or price."""
    if profile in _overrides:
        return _overrides[profile]
    return _configured(get_settings(), profile)


def set_llm_client(client: LlmClient | None, *profiles: LlmProfile) -> None:
    """Replace the client of the given profiles, of every profile when none is given (tests);
    `reset_llm_client` restores configuration."""
    for profile in profiles or LLM_PROFILES:
        _overrides[profile] = client


def reset_llm_client() -> None:
    _overrides.clear()


async def warm_llm_clients() -> None:
    """Prepares every configured profile's client for its first call - for Claude on Foundry,
    the Entra ID token and an open TLS connection, with no model call. A client without a
    `warm` method needs none. Never raises: a failed warm-up leaves the work to the first call."""
    for profile in LLM_PROFILES:
        try:
            warm = getattr(get_llm_client(profile), "warm", None)
            if warm is not None:
                await warm()
        except Exception as exc:
            logger.warning(
                "warming the %s language model client failed: %s", profile, type(exc).__name__
            )


def check_llm_configuration(settings: Settings) -> None:
    """Stops start-up when a provider is configured but a model it calls has no price.

    The Foundry providers price each profile's deployment; `anthropic` prices its model. A
    provider without its endpoint (`azure_foundry`, `anthropic_foundry`) or key (`anthropic`)
    is not an error: the model step answers `not_configured` and the grammar runs alone.
    """
    if not _provider_configured(settings):
        return
    for profile in LLM_PROFILES:
        model = _priced_model(settings, profile)
        if not isinstance(settings.llm_price_table.get(model), ModelPrice):
            raise LlmConfigurationError(
                f"ONTAIX_LLM_PRICE_TABLE has no token price for {model!r}, the {profile} "
                "profile's model"
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
    if settings.llm_provider in FOUNDRY_PROVIDERS:
        return settings.foundry_endpoint is not None
    key = settings.anthropic_api_key
    return key is not None and bool(key.get_secret_value())


def _priced_model(settings: Settings, profile: LlmProfile) -> str:
    """The model `profile` records and prices: the Foundry deployment called, else the model."""
    if settings.llm_provider in FOUNDRY_PROVIDERS:
        return settings.llm_profile(profile).deployment
    return settings.llm_model


def _configured(settings: Settings, profile: LlmProfile) -> LlmClient | None:
    price = settings.llm_price_table.get(_priced_model(settings, profile))
    if not _provider_configured(settings) or not isinstance(price, ModelPrice):
        return None
    chosen = settings.llm_profile(profile)
    if settings.llm_provider in FOUNDRY_PROVIDERS:
        fingerprint: tuple[object, ...] = (
            settings.llm_provider,
            price,
            settings.foundry_endpoint,
            chosen.deployment,
            chosen.reasoning_effort,
        )
    else:
        key = settings.anthropic_api_key.get_secret_value()  # type: ignore[union-attr]
        fingerprint = (
            settings.llm_provider,
            settings.llm_model,
            price,
            hashlib.sha256(key.encode()).hexdigest(),
        )
    cached = _cached.get(profile)
    if cached is None or cached[0] != fingerprint:
        cached = (fingerprint, _build(settings, chosen, price))
        _cached[profile] = cached
    return cached[1]


def _build(settings: Settings, chosen: LlmProfileSettings, price: ModelPrice) -> LlmClient:
    if settings.llm_provider == "azure_foundry":
        from app.clients.foundry_llm_client import FoundryLlmClient

        return FoundryLlmClient(
            endpoint=settings.foundry_endpoint or "",
            deployment=chosen.deployment,
            model=chosen.deployment,
            price=price,
            reasoning_effort=chosen.reasoning_effort,
        )
    if settings.llm_provider == "anthropic_foundry":
        from app.clients.anthropic_foundry_llm_client import (
            AnthropicFoundryLlmClient,
            foundry_messages_url,
        )

        return AnthropicFoundryLlmClient(
            base_url=foundry_messages_url(settings.foundry_endpoint or ""),
            deployment=chosen.deployment,
            price=price,
            reasoning_effort=chosen.reasoning_effort,
        )
    from app.clients.anthropic_llm_client import AnthropicLlmClient

    key = settings.anthropic_api_key.get_secret_value()  # type: ignore[union-attr]
    return AnthropicLlmClient(key, settings.llm_model, price)
