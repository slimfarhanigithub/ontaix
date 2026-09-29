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
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings, get_settings

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


class LlmClient(Protocol):
    provider: str
    model: str

    def estimate_input_tokens(self, request: LlmRequest) -> int: ...

    async def complete(self, request: LlmRequest) -> LlmAnswer: ...


_override: LlmClient | None = None
_override_set = False
_cached: tuple[tuple[str, str, float, str], LlmClient] | None = None


def get_llm_client() -> LlmClient | None:
    """The configured client, or None when the deployment has no provider key."""
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


def estimate_tokens(request: LlmRequest) -> int:
    """A provider-independent upper estimate of the request's input tokens."""
    assembled = request.system + request.user + json.dumps(request.output_schema)
    by_code_points = -(-len(assembled) // CODE_POINTS_PER_TOKEN)
    by_bytes = -(-len(assembled.encode("utf-8")) // BYTES_PER_TOKEN)
    return max(by_code_points, by_bytes)


def _configured(settings: Settings) -> LlmClient | None:
    global _cached
    if settings.llm_provider != "anthropic" or settings.anthropic_api_key is None:
        return None
    key = settings.anthropic_api_key.get_secret_value()
    if not key:
        return None
    key_digest = hashlib.sha256(key.encode()).hexdigest()
    fingerprint = (
        settings.llm_provider,
        settings.llm_model,
        key_digest,
    )
    if _cached is None or _cached[0] != fingerprint:
        from app.clients.anthropic_llm_client import AnthropicLlmClient

        _cached = (
            fingerprint,
            AnthropicLlmClient(key, settings.llm_model),
        )
    return _cached[1]
