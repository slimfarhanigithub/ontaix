"""The Anthropic implementation of the language model adapter.

One Messages API call per request, with the answer constrained to the request's JSON schema
(structured outputs). `complete_messages` holds the call so that the Foundry-hosted Claude
client makes it the same way. The wall clock of a call - DNS, connect, TLS, sending and reading
the last byte - is bounded by `asyncio.timeout` on top of the SDK's own timeout, and the SDK's
retries are 0, so a call never takes longer than the configured timeout. Structured outputs
keep optional properties optional, and Claude writes an empty string or list for one it means
to leave out; those are removed from the answer, so it has the shape the API validates. The
system prompt carries a `cache_control` breakpoint, so a provider holding it in its prompt
cache reads it at a tenth of the input price instead of processing it again; cache writes cost
1.25 times the input price. The SDK and HTTP loggers are held at WARNING and filtered, so
prompts, answers and authentication headers never reach a log.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal
from typing import Any

import anthropic

from app.clients.llm_client import (
    LlmAnswer,
    LlmProviderError,
    LlmRefused,
    LlmRequest,
    LlmTimeout,
    elapsed_ms,
    estimate_tokens,
)
from app.clients.llm_log_redaction import protect_loggers
from app.config import ModelPrice
from app.utilities.strict_json_schema import drop_optional_empties, to_strict

logger = logging.getLogger(__name__)

PROVIDER = "anthropic"
# Prices of prompt-cache tokens relative to the model's input price.
CACHE_WRITE_PRICE_FACTOR = Decimal("1.25")
CACHE_READ_PRICE_FACTOR = Decimal("0.1")

_REDACTING_FILTER = protect_loggers(("anthropic", "httpx2", "httpx", "httpcore"))


class AnthropicLlmClient:
    provider = PROVIDER

    def __init__(self, api_key: str, model: str, price: ModelPrice) -> None:
        self.model = model
        self._price = price
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)

    def __repr__(self) -> str:
        return f"AnthropicLlmClient(model={self.model!r})"

    def estimate_input_tokens(self, request: LlmRequest) -> int:
        return estimate_tokens(request)

    async def complete(self, request: LlmRequest) -> LlmAnswer:
        # Extraction is short and bounded by max_tokens; reasoning tokens would compete with
        # the answer for the same budget.
        return await complete_messages(
            self._client, self.model, self._price, request, {"thinking": {"type": "disabled"}}
        )


async def complete_messages(
    client: anthropic.AsyncAnthropic,
    model: str,
    price: ModelPrice,
    request: LlmRequest,
    options: dict[str, Any],
) -> LlmAnswer:
    """One Messages API call answering `request` with structured output; `options` are the
    thinking and effort parameters of the caller's model. Any client of the Anthropic SDK
    (first-party or Foundry) is used the same way."""
    started = time.monotonic()
    output_config: dict[str, Any] = {
        "format": {"type": "json_schema", "schema": request.output_schema},
        **options.get("output_config", {}),
    }
    extra = {k: v for k, v in options.items() if k != "output_config"}
    try:
        limit = request.timeout_seconds
        timed = client.with_options(timeout=anthropic.Timeout(limit, connect=limit))
        async with asyncio.timeout(limit):
            message = await timed.messages.create(
                model=model,
                max_tokens=request.max_output_tokens,
                system=[
                    {
                        "type": "text",
                        "text": request.system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": request.user}],
                output_config=output_config,
                **extra,
            )
    except (TimeoutError, anthropic.APITimeoutError) as exc:
        raise LlmTimeout("timeout", latency_ms=elapsed_ms(started)) from exc
    except anthropic.APIStatusError as exc:
        logger.warning("language model call refused with status %s", exc.status_code)
        raise LlmProviderError("status", latency_ms=elapsed_ms(started)) from exc
    except anthropic.APIConnectionError as exc:
        logger.warning("language model call failed to connect")
        raise LlmProviderError("connection", latency_ms=elapsed_ms(started)) from exc
    except anthropic.AnthropicError as exc:
        logger.warning("language model call failed: %s", type(exc).__name__)
        raise LlmProviderError("sdk", latency_ms=elapsed_ms(started)) from exc
    latency_ms = elapsed_ms(started)
    usage = message.usage
    cache_written = usage.cache_creation_input_tokens or 0
    cache_read = usage.cache_read_input_tokens or 0
    input_tokens = usage.input_tokens + cache_written + cache_read
    # Thinking tokens are part of output_tokens.
    output_tokens = usage.output_tokens
    cost = cached_cost_eur(price, usage.input_tokens, cache_written, cache_read, output_tokens)
    logger.debug(
        "%s answered in %d ms: input %d (cache write %d, cache read %d), output %d",
        model,
        latency_ms,
        input_tokens,
        cache_written,
        cache_read,
        output_tokens,
    )
    if message.stop_reason == "refusal":
        raise LlmRefused("refusal", input_tokens, output_tokens, cost, latency_ms)
    text = "".join(block.text for block in message.content if block.type == "text")
    return LlmAnswer(
        _without_optional_empties(text, request.output_schema),
        input_tokens,
        output_tokens,
        cost,
        latency_ms,
    )


def _without_optional_empties(text: str, schema: dict[str, Any]) -> str:
    """The answer without the empty strings and lists Claude writes for optional properties it
    leaves unset; text that is not JSON is returned as is."""
    try:
        data = json.loads(text)
    except ValueError:
        return text
    _, optional = to_strict(schema)
    return json.dumps(drop_optional_empties(data, optional), ensure_ascii=False)


def cached_cost_eur(
    price: ModelPrice, uncached: int, cache_written: int, cache_read: int, output: int
) -> float:
    """Estimated euros of a call whose input is partly written to or read from the prompt
    cache, rounded to 6 places."""
    input_cost = price.input_eur_per_mtok * (
        uncached + CACHE_WRITE_PRICE_FACTOR * cache_written + CACHE_READ_PRICE_FACTOR * cache_read
    )
    return float(round((input_cost + price.output_eur_per_mtok * output) / Decimal(1_000_000), 6))
