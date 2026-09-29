"""Claude on Azure AI Foundry behind the provider-neutral language model adapter.

The Anthropic SDK's Foundry client (`AsyncAnthropicFoundry`) calls the resource's Messages
endpoint (`https://<resource>.services.ai.azure.com/anthropic/`), addressed to the deployment
name. Authentication is keyless: an Entra ID bearer token for `https://ai.azure.com/.default`
from `DefaultAzureCredential`, acquired in a worker thread before every call. The call itself,
its structured output, timeout, zero retries and token accounting (thinking tokens counted as
output) are those of the first-party Anthropic client.

Reasoning effort maps to Claude's thinking settings: `None` sends no thinking or effort
parameter (the model's own default); `none` disables thinking, which some models refuse;
`minimal`, `low`, `medium` and `high` turn adaptive thinking on with that effort (`minimal`
is sent as `low`, the lowest effort Claude takes).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import anthropic

from app.clients.anthropic_llm_client import complete_messages
from app.clients.llm_client import LlmAnswer, LlmRequest, estimate_tokens
from app.clients.llm_log_redaction import protect_loggers
from app.config import ModelPrice, ReasoningEffort

PROVIDER = "anthropic_foundry"
TOKEN_SCOPE = "https://ai.azure.com/.default"

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
        self._client = anthropic.AsyncAnthropicFoundry(
            base_url=base_url, azure_ad_token_provider=entra_token_provider(), max_retries=0
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
    """An async source of Entra ID bearer tokens for Claude on Foundry."""
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    token = get_bearer_token_provider(DefaultAzureCredential(), TOKEN_SCOPE)

    async def provide() -> str:
        return await asyncio.to_thread(token)

    return provide
