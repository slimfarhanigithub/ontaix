"""The Azure AI Foundry implementation of the language model adapter.

One Chat Completions call per request to the Foundry resource's OpenAI v1 endpoint
(`<endpoint>/openai/v1/`) through the official `openai` SDK, addressed to the model deployment.
Authentication is keyless: an Entra ID bearer token for `https://cognitiveservices.azure.com/.default`
from `DefaultAzureCredential` (the workload identity in the cluster, the `az login` session
locally), served by the process-wide token cache, which calls the credential only when it holds
no valid token.

The answer is constrained by `response_format` of type `json_schema` with `strict` true. Strict
mode needs every property listed as required, so the request's schema is sent in its strict form
(optional properties nullable) and the `null` values the model writes for them are removed from
the answer before it is returned. The wall clock of a call - token acquisition, DNS, connect,
TLS, sending and reading the last byte - is bounded by `asyncio.timeout` on top of the SDK's own
timeout. The SDK's retries are 0; a 429 or 503 is retried by `call_with_retries` within that
same wall clock, and only the answering attempt reports tokens. Token counts are the response's
`usage`: `prompt_tokens` as input (cached tokens included) and `completion_tokens` as output
(reasoning tokens included).
The SDK, Azure and HTTP loggers are held at WARNING and filtered, so prompts, answers and tokens
never reach a log.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

import openai
from openai.types.chat import ChatCompletion

from app.clients.entra_token_client import shared_token_cache
from app.clients.llm_client import (
    LlmAnswer,
    LlmProviderError,
    LlmRefused,
    LlmRequest,
    LlmTimeout,
    cost_eur,
    elapsed_ms,
    estimate_tokens,
)
from app.clients.llm_log_redaction import protect_loggers
from app.clients.llm_retry import call_with_retries
from app.config import ModelPrice, ReasoningEffort
from app.utilities.strict_json_schema import drop_optional_nulls, to_strict

logger = logging.getLogger(__name__)

PROVIDER = "azure_foundry"
TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"
SCHEMA_NAME = "answer"
# The finish reason, and the error code of a refused request, when the content filter blocks it.
CONTENT_FILTER = "content_filter"

TokenProvider = Callable[[], Awaitable[str]]

_REDACTING_FILTER = protect_loggers(
    ("openai", "azure", "msal", "httpx2", "httpx", "httpcore", "urllib3")
)


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
        reasoning_effort: ReasoningEffort,
    ) -> None:
        self.model = model
        self._deployment = deployment
        self._price = price
        self._reasoning_effort = reasoning_effort
        self._client = openai.AsyncOpenAI(
            base_url=f"{endpoint.rstrip('/')}/openai/v1/",
            api_key=_guarded(entra_token_provider()),
            max_retries=0,
        )

    def __repr__(self) -> str:
        return f"FoundryLlmClient(deployment={self._deployment!r}, model={self.model!r})"

    def estimate_input_tokens(self, request: LlmRequest) -> int:
        return estimate_tokens(request)

    async def complete(self, request: LlmRequest) -> LlmAnswer:
        started = time.monotonic()
        schema, optional = to_strict(request.output_schema)

        async def attempt(remaining: float) -> ChatCompletion:
            client = self._client.with_options(timeout=openai.Timeout(remaining, connect=remaining))
            return await client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user},
                ],
                max_completion_tokens=request.max_output_tokens,
                reasoning_effort=self._reasoning_effort,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": SCHEMA_NAME, "strict": True, "schema": schema},
                },
                store=False,
            )

        try:
            limit = request.timeout_seconds
            async with asyncio.timeout(limit):
                completion = await call_with_retries(
                    attempt, started + limit, openai.APIStatusError
                )
        except (TimeoutError, openai.APITimeoutError) as exc:
            raise LlmTimeout("timeout", latency_ms=elapsed_ms(started)) from exc
        except _CredentialFailure as exc:
            logger.warning("language model call failed: no Entra ID token was acquired")
            raise LlmProviderError("credential", latency_ms=elapsed_ms(started)) from exc
        except openai.APIStatusError as exc:
            logger.warning("language model call refused with status %s", exc.status_code)
            if getattr(exc, "code", None) == CONTENT_FILTER:
                raise LlmRefused("refusal", latency_ms=elapsed_ms(started)) from exc
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
        if choice.message.refusal or choice.finish_reason == CONTENT_FILTER:
            raise LlmRefused("refusal", input_tokens, output_tokens, cost, latency_ms)
        text = _without_optional_nulls(choice.message.content or "", optional)
        return LlmAnswer(text, input_tokens, output_tokens, cost, latency_ms)


def entra_token_provider() -> TokenProvider:
    """An async source of Entra ID bearer tokens for Azure AI services, shared by every client
    of the process."""
    return shared_token_cache(TOKEN_SCOPE).token


def _guarded(provider: TokenProvider) -> TokenProvider:
    async def provide() -> str:
        try:
            return await provider()
        except Exception as exc:
            # The credential chain's messages name environment and account details; only the
            # failure's type is kept.
            raise _CredentialFailure(type(exc).__name__) from None

    return provide


def _without_optional_nulls(text: str, optional: frozenset[str]) -> str:
    """The answer in the original schema's shape; text that is not JSON is returned as is, and
    fails the API's validation."""
    try:
        data = json.loads(text)
    except ValueError:
        return text
    return json.dumps(drop_optional_nulls(data, optional), ensure_ascii=False)
