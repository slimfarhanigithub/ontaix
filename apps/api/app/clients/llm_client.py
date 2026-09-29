"""Provider-neutral language model adapter: one request in, JSON text and token counts out.

The rest of the API sees only this module. A request carries the system instructions, one user
message and the JSON schema the answer must follow; the answer carries the raw JSON text, token
counts, the estimated euro cost and the latency. A timeout or a provider failure raises
`LlmTimeout` or `LlmProviderError`, each with the tokens the provider reported (0 when none).
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

from app.config import ModelPrice, Settings, get_settings

logger = logging.getLogger(__name__)

# The input estimate is the larger of code points / 2 (Latin scripts) and UTF-8 bytes / 3
# (scripts where one character is a token or more), so a reservation errs on counting too much.
CODE_POINTS_PER_TOKEN = 2
BYTES_PER_TOKEN = 3


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


class LlmConfigurationError(RuntimeError):
    """The configured provider cannot run: raised at start-up, never during a request."""


class LlmClient(Protocol):
    provider: str
    model: str

    def estimate_input_tokens(self, request: LlmRequest) -> int: ...

    async def complete(self, request: LlmRequest) -> LlmAnswer: ...


_override: LlmClient | None = None
_override_set = False
_cached: tuple[tuple[object, ...], LlmClient] | None = None


def get_llm_client() -> LlmClient | None:
    """The configured client, or None when the provider has no endpoint, key or price."""
    if _override_set:
        return _override
    return _configured(get_settings())


def set_llm_client(client: LlmClient | None) -> None:
    """Replace the configured client (tests); `reset_llm_client` restores configuration."""
    global _override, _override_set
    _override, _override_set = client, True


def reset_llm_client() -> None:
    global _override, _override_set
    _override, _override_set = None, False


def check_llm_configuration(settings: Settings) -> None:
    """Stops start-up when a provider is configured but its model has no price.

    A provider without its endpoint (`azure_foundry`) or key (`anthropic`) is not an error: the
    model step answers `not_configured` and the grammar runs alone.
    """
    if _provider_configured(settings) and settings.llm_model not in settings.llm_price_table:
        raise LlmConfigurationError(
            f"ONTAIX_LLM_PRICE_TABLE has no price for ONTAIX_LLM_MODEL {settings.llm_model!r}"
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
    """Milliseconds since `started` (a `time.monotonic()` value), capped at one minute."""
    return min(60_000, max(0, int((time.monotonic() - started) * 1000)))


def _provider_configured(settings: Settings) -> bool:
    if settings.llm_provider == "azure_foundry":
        return settings.foundry_endpoint is not None
    key = settings.anthropic_api_key
    return key is not None and bool(key.get_secret_value())


def _configured(settings: Settings) -> LlmClient | None:
    global _cached
    price = settings.llm_price_table.get(settings.llm_model)
    if not _provider_configured(settings) or price is None:
        return None
    if settings.llm_provider == "azure_foundry":
        fingerprint: tuple[object, ...] = (
            settings.llm_provider,
            settings.llm_model,
            price,
            settings.foundry_endpoint,
            settings.foundry_deployment,
            settings.foundry_reasoning_effort,
        )
    else:
        key = settings.anthropic_api_key.get_secret_value()  # type: ignore[union-attr]
        fingerprint = (
            settings.llm_provider,
            settings.llm_model,
            price,
            hashlib.sha256(key.encode()).hexdigest(),
        )
    if _cached is None or _cached[0] != fingerprint:
        _cached = (fingerprint, _build(settings, price))
    return _cached[1]


def _build(settings: Settings, price: ModelPrice) -> LlmClient:
    if settings.llm_provider == "azure_foundry":
        from app.clients.foundry_llm_client import FoundryLlmClient

        return FoundryLlmClient(
            endpoint=settings.foundry_endpoint or "",
            deployment=settings.foundry_deployment,
            model=settings.llm_model,
            price=price,
            reasoning_effort=settings.foundry_reasoning_effort,
        )
    from app.clients.anthropic_llm_client import AnthropicLlmClient

    key = settings.anthropic_api_key.get_secret_value()  # type: ignore[union-attr]
    return AnthropicLlmClient(key, settings.llm_model, price)
