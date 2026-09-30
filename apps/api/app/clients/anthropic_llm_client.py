"""The Anthropic implementation of the language model adapter.

One Messages API call per request, whole or streamed, with the answer constrained to the
request's JSON schema (structured outputs). `complete_messages` and `stream_messages` hold the
call so that the Foundry-hosted Claude client makes it the same way. The wall clock of a call -
DNS, connect, TLS, sending and reading the last byte - is bounded by `asyncio.timeout` on top
of the SDK's own timeout, and the SDK's retries are 0, so a call never takes longer than the
configured timeout; a 429 or 503 is retried by `call_with_retries` within that same wall clock.
The schema is sent in its required form: every property required, an optional string or list
written empty when unset and any other optional property nullable, within Claude's cap of 16
union-typed properties. With optional properties left optional, Claude drops properties it
needs (a `rel` intent without its `object`) and fills others with invented values, so most
answers fail validation. The `null` values and the empty strings and lists written for unset
optional properties are removed from the answer, so it has the shape the API validates. The
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
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import anthropic
from anthropic.types import Message

from app.clients.llm_client import (
    LlmAnswer,
    LlmProviderError,
    LlmRefused,
    LlmRequest,
    LlmTimeout,
    TextListener,
    elapsed_ms,
    estimate_tokens,
)
from app.clients.llm_log_redaction import protect_loggers
from app.clients.llm_retry import call_with_retries
from app.config import ModelPrice
from app.utilities.strict_json_schema import (
    drop_optional_empties,
    drop_optional_nulls,
    to_required_form,
)

logger = logging.getLogger(__name__)

PROVIDER = "anthropic"
# Prices of prompt-cache tokens relative to the model's input price.
CACHE_WRITE_PRICE_FACTOR = Decimal("1.25")
CACHE_READ_PRICE_FACTOR = Decimal("0.1")

# Extraction is short and bounded by max_tokens; reasoning tokens would compete with the answer
# for the same budget.
_OPTIONS: dict[str, Any] = {"thinking": {"type": "disabled"}}

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
        return await complete_messages(self._client, self.model, self._price, request, _OPTIONS)

    async def stream(self, request: LlmRequest, on_text: TextListener) -> LlmAnswer:
        return await stream_messages(
            self._client, self.model, self._price, request, _OPTIONS, on_text
        )

    def answer_text(self, raw: str, request: LlmRequest) -> str:
        return answer_text(raw, request)


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
    arguments = _arguments(model, request, options)

    async def attempt(remaining: float) -> Message:
        timed = client.with_options(timeout=anthropic.Timeout(remaining, connect=remaining))
        return await timed.messages.create(**arguments)

    message = await _call(request, started, attempt)
    return _answer(message, model, price, request, started)


async def stream_messages(
    client: anthropic.AsyncAnthropic,
    model: str,
    price: ModelPrice,
    request: LlmRequest,
    options: dict[str, Any],
    on_text: TextListener,
) -> LlmAnswer:
    """The call of `complete_messages` with the answer streamed: `on_text` receives the answer
    text received so far after every text fragment, and the final message gives the answer and
    its usage exactly as the whole call does."""
    started = time.monotonic()
    arguments = _arguments(model, request, options)

    async def attempt(remaining: float) -> Message:
        timed = client.with_options(timeout=anthropic.Timeout(remaining, connect=remaining))
        async with timed.messages.stream(**arguments) as stream:
            text = ""
            async for fragment in stream.text_stream:
                text += fragment
                await on_text(text)
            return await stream.get_final_message()

    message = await _call(request, started, attempt)
    return _answer(message, model, price, request, started)


def answer_text(raw: str, request: LlmRequest) -> str:
    """A raw answer in the shape the API validates: see `_without_optional_empties`."""
    return _without_optional_empties(raw, request.output_schema)


def _arguments(model: str, request: LlmRequest, options: dict[str, Any]) -> dict[str, Any]:
    required, _ = to_required_form(request.output_schema)
    output_config: dict[str, Any] = {
        "format": {"type": "json_schema", "schema": required},
        **options.get("output_config", {}),
    }
    extra = {k: v for k, v in options.items() if k != "output_config"}
    return {
        "model": model,
        "max_tokens": request.max_output_tokens,
        "system": [
            {
                "type": "text",
                "text": request.system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": request.user}],
        "output_config": output_config,
        **extra,
    }


async def _call(
    request: LlmRequest, started: float, attempt: Callable[[float], Awaitable[Message]]
) -> Message:
    """`attempt` within the request's wall clock, with bounded 429 and 503 retries, and every
    failure raised as the adapter's error."""
    try:
        limit = request.timeout_seconds
        async with asyncio.timeout(limit):
            return await call_with_retries(attempt, started + limit, anthropic.APIStatusError)
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


def _answer(
    message: Message, model: str, price: ModelPrice, request: LlmRequest, started: float
) -> LlmAnswer:
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
    return LlmAnswer(answer_text(text, request), input_tokens, output_tokens, cost, latency_ms)


def _without_optional_empties(text: str, schema: dict[str, Any]) -> str:
    """The answer without the `null` values, empty strings and empty lists Claude writes for
    optional properties it leaves unset; text that is not JSON is returned as is."""
    try:
        data = json.loads(text)
    except ValueError:
        return text
    _, optional = to_required_form(schema)
    kept = drop_optional_empties(drop_optional_nulls(data, optional), optional)
    return json.dumps(kept, ensure_ascii=False)


def cached_cost_eur(
    price: ModelPrice, uncached: int, cache_written: int, cache_read: int, output: int
) -> float:
    """Estimated euros of a call whose input is partly written to or read from the prompt
    cache, rounded to 6 places."""
    input_cost = price.input_eur_per_mtok * (
        uncached + CACHE_WRITE_PRICE_FACTOR * cache_written + CACHE_READ_PRICE_FACTOR * cache_read
    )
    return float(round((input_cost + price.output_eur_per_mtok * output) / Decimal(1_000_000), 6))
