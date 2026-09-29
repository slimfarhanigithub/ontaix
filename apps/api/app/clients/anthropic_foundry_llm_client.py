"""Claude on Azure AI Foundry behind the provider-neutral language model adapter.

The Anthropic SDK's Foundry client (`AsyncAnthropicFoundry`) calls the resource's Messages
endpoint (`https://<resource>.services.ai.azure.com/anthropic/`), addressed to the deployment
name. Authentication is keyless: an Entra ID bearer token for `https://ai.azure.com/.default`
from the process-wide token cache, which calls `DefaultAzureCredential` only when it holds no
valid token. Each client keeps one HTTP connection pool whose idle connections live for
`KEEPALIVE_SECONDS`, so a call made a minute after the last one skips DNS, TCP and TLS; `warm`
acquires the token and opens a connection without a model call. The call itself, its
structured output, prompt caching, timeout, zero retries and token accounting (thinking tokens
counted as output) are those of the first-party Anthropic client.

Reasoning effort maps to Claude's thinking settings: `None` sends no thinking or effort
parameter (the model's own default); `none` disables thinking, which some models refuse;
`minimal`, `low`, `medium` and `high` turn adaptive thinking on with that effort (`minimal`
is sent as `low`, the lowest effort Claude takes).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import anthropic
import httpx2

from app.clients.anthropic_llm_client import complete_messages
from app.clients.entra_token_client import shared_token_cache
from app.clients.llm_client import LlmAnswer, LlmRequest, estimate_tokens
from app.clients.llm_log_redaction import protect_loggers
from app.config import ModelPrice, ReasoningEffort

logger = logging.getLogger(__name__)

PROVIDER = "anthropic_foundry"
TOKEN_SCOPE = "https://ai.azure.com/.default"
# Idle connections stay open this long; the Foundry front end keeps them longer.
KEEPALIVE_SECONDS = 120.0
WARM_UP_TIMEOUT_SECONDS = 10.0

_REDACTING_FILTER = protect_loggers(
    ("anthropic", "azure", "msal", "httpx2", "httpx", "httpcore", "urllib3")
)


class AnthropicFoundryLlmClient:
    provider = PROVIDER

    def __init__(
        self,
        base_url: str,
        deployment: str,
        price: ModelPrice,
        reasoning_effort: ReasoningEffort | None,
    ) -> None:
        self.model = deployment
        self._price = price
        self._options = thinking_options(reasoning_effort)
        self._base_url = base_url
        self._http = anthropic.DefaultAsyncHttpxClient(
            limits=httpx2.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=KEEPALIVE_SECONDS,
            )
        )
        self._token = entra_token_provider()
        self._client = anthropic.AsyncAnthropicFoundry(
            base_url=base_url,
            azure_ad_token_provider=self._token,
            max_retries=0,
            http_client=self._http,
        )

    def __repr__(self) -> str:
        return f"AnthropicFoundryLlmClient(model={self.model!r})"

    @property
    def capabilities(self) -> dict[str, object]:
        return {"outputMode": "json_schema", **self._options}

    def estimate_input_tokens(self, request: LlmRequest) -> int:
        return estimate_tokens(request)

    async def complete(self, request: LlmRequest) -> LlmAnswer:
        return await complete_messages(
            self._client, self.model, self._price, request, self._options
        )

    async def warm(self) -> None:
        """Acquires the Entra ID token and opens a TLS connection to the Foundry host with an
        unauthenticated GET of the Messages base URL: no model call, no cost."""
        started = time.perf_counter()
        await self._token()
        token_ms = int((time.perf_counter() - started) * 1000)
        await self._http.get(self._base_url, timeout=WARM_UP_TIMEOUT_SECONDS)
        logger.debug(
            "%s warmed: token %d ms, connection %d ms",
            self.model,
            token_ms,
            int((time.perf_counter() - started) * 1000) - token_ms,
        )


def foundry_messages_url(endpoint: str) -> str:
    """The Messages base URL of a Foundry resource from any of its endpoints."""
    host = endpoint.split("//", 1)[-1].split("/", 1)[0]
    resource = host.split(".", 1)[0]
    return f"https://{resource}.services.ai.azure.com/anthropic/"


def thinking_options(effort: ReasoningEffort | None) -> dict[str, Any]:
    if effort is None:
        return {}
    if effort == "none":
        return {"thinking": {"type": "disabled"}}
    level = "low" if effort == "minimal" else effort
    return {"thinking": {"type": "adaptive"}, "output_config": {"effort": level}}


def entra_token_provider() -> Callable[[], Awaitable[str]]:
    """An async source of Entra ID bearer tokens for Claude on Foundry, shared by every client
    of the process."""
    return shared_token_cache(TOKEN_SCOPE).token
