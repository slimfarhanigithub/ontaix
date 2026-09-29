"""The Azure AI Foundry implementation of the language model adapter.

One Chat Completions call per request to the Foundry resource's OpenAI v1 endpoint
(`<endpoint>/openai/v1/`) through the official `openai` SDK, addressed to the model deployment.
Authentication is keyless: an Entra ID bearer token for `https://cognitiveservices.azure.com/.default`
from `DefaultAzureCredential` (the workload identity in the cluster, the `az login` session
locally), acquired before every call and cached by the credential until it nears expiry.

The answer is constrained by `response_format` of type `json_schema` with `strict` true. Strict
mode needs every property listed as required, so the request's schema is sent in its strict form
(optional properties nullable) and the `null` values the model writes for them are removed from
the answer before it is returned. The wall clock of a call - token acquisition, DNS, connect,
TLS, sending and reading the last byte - is bounded by `asyncio.timeout` on top of the SDK's own
timeout, and the SDK's retries are 0. Token counts are the response's `usage`: `prompt_tokens`
as input (cached tokens included) and `completion_tokens` as output (reasoning tokens included).
The SDK, Azure and HTTP loggers are held at WARNING and filtered, so prompts, answers and tokens
never reach a log.

Capability fallback: a deployment that answers 400 because it does not support what was asked
is asked again, within the same wall clock, without it, and the client remembers the choice for
its later calls. The output mode steps down from strict `json_schema` to `json_object` to a
prompt-only JSON instruction (both carrying the schema in the system message); an unsupported
`store` or `reasoning_effort` is dropped; an unsupported `max_completion_tokens` is sent as
`max_tokens`. A 400 steps down only when its message says the option is not supported; any other
400, and every other status, is one attempt. Whatever the mode, the API
validates the answer against the full contract afterwards. `reasoning_effort` None sends none.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import openai

from app.clients.llm_client import (
    LlmAnswer,
    LlmProviderError,
    LlmRequest,
    LlmTimeout,
    cost_eur,
    elapsed_ms,
    estimate_tokens,
)
from app.clients.llm_log_redaction import protect_loggers
from app.config import ModelPrice, ReasoningEffort
from app.utilities.strict_json_schema import drop_optional_nulls, to_strict

logger = logging.getLogger(__name__)

PROVIDER = "azure_foundry"
TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"
SCHEMA_NAME = "answer"

OutputMode = Literal["json_schema", "json_object", "prompt"]
OUTPUT_MODES: tuple[OutputMode, ...] = ("json_schema", "json_object", "prompt")
# One call steps down at most this many times before its 400 stands.
MAX_ADAPTATIONS = 6
JSON_INSTRUCTION = (
    "\n\nAnswer with one JSON object and nothing else: no prose, no markdown fence. It must "
    "follow this JSON Schema:\n"
)

TokenProvider = Callable[[], Awaitable[str]]

_REDACTING_FILTER = protect_loggers(
    ("openai", "azure", "msal", "httpx2", "httpx", "httpcore", "urllib3")
)
_FORMAT_REFUSED = re.compile(r"response_format|json_schema|json_object|structured output", re.I)
# A 400 steps down only when it says an option is unsupported, never for an invalid value.
_UNSUPPORTED = re.compile(
    r"unsupported|not supported|does not support|unrecognized|unknown (?:parameter|field|argument)"
    r"|not allowed|not permitted|extra (?:inputs|fields)|unexpected (?:keyword|parameter|field)"
)
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S | re.I)


class _CredentialFailure(Exception):
    """No Entra ID token could be acquired; carries no detail of the credential chain."""


class FoundryLlmClient:
    provider = PROVIDER

    def __init__(
        self,
        endpoint: str,
        deployment: str,
        model: str,
        price: ModelPrice,
        reasoning_effort: ReasoningEffort | None,
        output_modes: tuple[OutputMode, ...] = OUTPUT_MODES,
    ) -> None:
        self.model = model
        self._deployment = deployment
        self._price = price
        self._reasoning_effort = reasoning_effort
        self._modes: list[OutputMode] = list(output_modes)
        self._send_store = True
        self._token_parameter = "max_completion_tokens"
        self._client = openai.AsyncOpenAI(
            base_url=f"{endpoint.rstrip('/')}/openai/v1/",
            api_key=_guarded(entra_token_provider()),
            max_retries=0,
        )

    def __repr__(self) -> str:
        return f"FoundryLlmClient(deployment={self._deployment!r}, model={self.model!r})"

    @property
    def output_mode(self) -> OutputMode:
        """The output mode the next call uses: the first one the deployment has not refused."""
        return self._modes[0]

    @property
    def capabilities(self) -> dict[str, object]:
        """What the deployment accepted so far, for reports."""
        return {
            "outputMode": self.output_mode,
            "reasoningEffort": self._reasoning_effort,
            "store": self._send_store,
            "tokenParameter": self._token_parameter,
        }

    def estimate_input_tokens(self, request: LlmRequest) -> int:
        return estimate_tokens(request)

    async def complete(self, request: LlmRequest) -> LlmAnswer:
        started = time.monotonic()
        schema, optional = to_strict(request.output_schema)
        try:
            limit = request.timeout_seconds
            client = self._client.with_options(timeout=openai.Timeout(limit, connect=limit))
            async with asyncio.timeout(limit):
                completion, mode = await self._create(client, request, schema)
        except (TimeoutError, openai.APITimeoutError) as exc:
            raise LlmTimeout("timeout", latency_ms=elapsed_ms(started)) from exc
        except _CredentialFailure as exc:
            logger.warning("language model call failed: no Entra ID token was acquired")
            raise LlmProviderError("credential", latency_ms=elapsed_ms(started)) from exc
        except openai.APIStatusError as exc:
            logger.warning("language model call refused with status %s", exc.status_code)
            raise LlmProviderError("status", latency_ms=elapsed_ms(started)) from exc
        except openai.APIConnectionError as exc:
            logger.warning("language model call failed to connect")
            raise LlmProviderError("connection", latency_ms=elapsed_ms(started)) from exc
        except openai.OpenAIError as exc:
            logger.warning("language model call failed: %s", type(exc).__name__)
            raise LlmProviderError("sdk", latency_ms=elapsed_ms(started)) from exc
        latency_ms = elapsed_ms(started)
        usage = completion.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = cost_eur(self._price, input_tokens, output_tokens)
        if not completion.choices:
            raise LlmProviderError("empty", input_tokens, output_tokens, cost, latency_ms)
        choice = completion.choices[0]
        if getattr(choice.message, "refusal", None) or choice.finish_reason == "content_filter":
            raise LlmProviderError("refusal", input_tokens, output_tokens, cost, latency_ms)
        content = choice.message.content or ""
        if mode != "json_schema":
            content = _unfenced(content)
        text = _without_optional_nulls(content, optional)
        return LlmAnswer(text, input_tokens, output_tokens, cost, latency_ms)

    async def _create(
        self, client: openai.AsyncOpenAI, request: LlmRequest, schema: dict[str, Any]
    ) -> tuple[Any, OutputMode]:
        for _ in range(MAX_ADAPTATIONS):
            mode = self.output_mode
            try:
                completion = await client.chat.completions.create(
                    **self._arguments(request, schema, mode)
                )
                return completion, mode
            except openai.BadRequestError as exc:
                if not self._adapt(exc):
                    raise
        return await client.chat.completions.create(
            **self._arguments(request, schema, self.output_mode)
        ), self.output_mode

    def _arguments(
        self, request: LlmRequest, schema: dict[str, Any], mode: OutputMode
    ) -> dict[str, Any]:
        system = request.system
        if mode != "json_schema":
            system += JSON_INSTRUCTION + json.dumps(request.output_schema, ensure_ascii=False)
        arguments: dict[str, Any] = {
            "model": self._deployment,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": request.user},
            ],
            self._token_parameter: request.max_output_tokens,
        }
        if self._reasoning_effort is not None:
            arguments["reasoning_effort"] = self._reasoning_effort
        if self._send_store:
            arguments["store"] = False
        if mode == "json_schema":
            arguments["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": SCHEMA_NAME, "strict": True, "schema": schema},
            }
        elif mode == "json_object":
            arguments["response_format"] = {"type": "json_object"}
        return arguments

    def _adapt(self, exc: openai.BadRequestError) -> bool:
        """Steps down from what a 400 says the deployment does not support; False when the
        400 names nothing the client can do without."""
        message = _error_text(exc)
        if not _UNSUPPORTED.search(message):
            return False
        if "max_completion_tokens" in message and self._token_parameter != "max_tokens":
            self._token_parameter = "max_tokens"
        elif "reasoning_effort" in message and self._reasoning_effort is not None:
            self._reasoning_effort = None
        elif re.search(r"\bstore\b", message) and self._send_store:
            self._send_store = False
        elif _FORMAT_REFUSED.search(message) and len(self._modes) > 1:
            self._modes.pop(0)
        else:
            return False
        logger.warning(
            "deployment %s refused a request option; retrying with %s",
            self._deployment,
            self.capabilities,
        )
        return True


def entra_token_provider() -> TokenProvider:
    """An async source of Entra ID bearer tokens for Azure AI services.

    The synchronous `DefaultAzureCredential` runs in a worker thread, so a slow credential
    chain never blocks the event loop and the call's timeout still applies to it.
    """
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    token = get_bearer_token_provider(DefaultAzureCredential(), TOKEN_SCOPE)

    async def provide() -> str:
        return await asyncio.to_thread(token)

    return provide


def _guarded(provider: TokenProvider) -> TokenProvider:
    async def provide() -> str:
        try:
            return await provider()
        except Exception as exc:
            # The credential chain's messages name environment and account details; only the
            # failure's type is kept.
            raise _CredentialFailure(type(exc).__name__) from None

    return provide


def _error_text(exc: openai.BadRequestError) -> str:
    """The provider's error message and parameter name, lower case; never logged."""
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error", body) if isinstance(body.get("error", body), dict) else {}
    parts = [str(exc.message or ""), str(error.get("message") or ""), str(error.get("param") or "")]
    return " ".join(parts).lower()


def _unfenced(text: str) -> str:
    """The JSON inside a markdown code fence, which a model without a response format may add."""
    match = _FENCE.match(text)
    return match.group(1) if match else text.strip()


def _without_optional_nulls(text: str, optional: frozenset[str]) -> str:
    """The answer in the original schema's shape; text that is not JSON is returned as is, and
    fails the API's validation."""
    try:
        data = json.loads(text)
    except ValueError:
        return text
    return json.dumps(drop_optional_nulls(data, optional), ensure_ascii=False)
