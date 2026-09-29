"""The Anthropic implementation of the language model adapter.

One Messages API call per request, with the answer constrained to the request's JSON schema
(structured outputs). The wall clock of a call - DNS, connect, TLS, sending and reading the last
byte - is bounded by `asyncio.timeout` on top of the SDK's own timeout, and the SDK's retries
are 0, so a call never takes longer than the configured timeout. The SDK and HTTP loggers are
held at WARNING and filtered, so prompts, answers and authentication headers never reach a log.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from decimal import Decimal

import anthropic

from app.clients.llm_client import (
    LlmAnswer,
    LlmProviderError,
    LlmRequest,
    LlmTimeout,
    estimate_tokens,
)

logger = logging.getLogger(__name__)

PROVIDER = "anthropic"

# Estimated euros per million input and output tokens, by model; an estimate for Cost
# management, not the provider's invoice. An unknown model is priced at the highest rate.
PRICE_EUR_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-5": (Decimal("1.85"), Decimal("9.25")),
    "claude-sonnet-4-6": (Decimal("2.78"), Decimal("13.88")),
    "claude-haiku-4-5": (Decimal("0.93"), Decimal("4.63")),
    "claude-opus-5-5": (Decimal("3.70"), Decimal("18.50")),
    "claude-opus-5": (Decimal("4.63"), Decimal("23.13")),
    "claude-fable-5-1": (Decimal("9.25"), Decimal("46.25")),
}
UNKNOWN_MODEL_PRICE = (Decimal("9.25"), Decimal("46.25"))

_SECRET_PATTERN = re.compile(r"(?i)(x-api-key|authorization)(['\"]?\s*[:=]\s*['\"]?)[^'\",\s}]+")


class _RedactingFilter(logging.Filter):
    """Drops debug records (they carry request bodies) and masks authentication headers."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.INFO:
            return False
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        # The message is formatted before it is masked, so a header value passed as an argument
        # is masked too.
        record.msg = _SECRET_PATTERN.sub(r"\1\2[redacted]", message)
        record.args = None
        return True


# A logger's filters do not apply to records of its child loggers, so the filter is attached
# to the SDK and HTTP loggers and to every child logger they have registered.
_SDK_LOGGERS = ("anthropic", "httpx2", "httpx", "httpcore")
_REDACTING_FILTER = _RedactingFilter()
for _name in _SDK_LOGGERS:
    logging.getLogger(_name).setLevel(logging.WARNING)
for _name in [
    n
    for n in (*_SDK_LOGGERS, *list(logging.root.manager.loggerDict))
    if n.split(".")[0] in _SDK_LOGGERS
]:
    _logger = logging.getLogger(_name)
    if _REDACTING_FILTER not in _logger.filters:
        _logger.addFilter(_REDACTING_FILTER)


class AnthropicLlmClient:
    provider = PROVIDER

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)

    def __repr__(self) -> str:
        return f"AnthropicLlmClient(model={self.model!r})"

    def estimate_input_tokens(self, request: LlmRequest) -> int:
        return estimate_tokens(request)

    async def complete(self, request: LlmRequest) -> LlmAnswer:
        started = time.monotonic()
        try:
            limit = request.timeout_seconds
            client = self._client.with_options(timeout=anthropic.Timeout(limit, connect=limit))
            async with asyncio.timeout(limit):
                message = await client.messages.create(
                    model=self.model,
                    max_tokens=request.max_output_tokens,
                    # Extraction is short and bounded by max_tokens; reasoning tokens would
                    # compete with the answer for the same budget.
                    thinking={"type": "disabled"},
                    system=request.system,
                    messages=[{"role": "user", "content": request.user}],
                    output_config={
                        "format": {"type": "json_schema", "schema": request.output_schema}
                    },
                )
        except (TimeoutError, anthropic.APITimeoutError) as exc:
            raise LlmTimeout("timeout", latency_ms=_elapsed_ms(started)) from exc
        except anthropic.APIStatusError as exc:
            logger.warning("language model call refused with status %s", exc.status_code)
            raise LlmProviderError("status", latency_ms=_elapsed_ms(started)) from exc
        except anthropic.APIConnectionError as exc:
            logger.warning("language model call failed to connect")
            raise LlmProviderError("connection", latency_ms=_elapsed_ms(started)) from exc
        except anthropic.AnthropicError as exc:
            logger.warning("language model call failed: %s", type(exc).__name__)
            raise LlmProviderError("sdk", latency_ms=_elapsed_ms(started)) from exc
        latency_ms = _elapsed_ms(started)
        usage = message.usage
        input_tokens = (
            usage.input_tokens
            + (usage.cache_creation_input_tokens or 0)
            + (usage.cache_read_input_tokens or 0)
        )
        output_tokens = usage.output_tokens
        cost = _cost_eur(self.model, input_tokens, output_tokens)
        if message.stop_reason == "refusal":
            raise LlmProviderError("refusal", input_tokens, output_tokens, cost, latency_ms)
        text = "".join(block.text for block in message.content if block.type == "text")
        return LlmAnswer(text, input_tokens, output_tokens, cost, latency_ms)


def _cost_eur(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICE_EUR_PER_MTOK.get(model, UNKNOWN_MODEL_PRICE)
    cost = (price_in * input_tokens + price_out * output_tokens) / Decimal(1_000_000)
    return float(round(cost, 6))


def _elapsed_ms(started: float) -> int:
    return min(60_000, max(0, int((time.monotonic() - started) * 1000)))
