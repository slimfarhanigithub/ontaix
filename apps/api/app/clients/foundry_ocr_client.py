"""The Azure AI Foundry implementation of the OCR adapter: a Mistral document model.

One call per import to the Foundry resource's Mistral OCR route
(`https://<resource>.services.ai.azure.com/providers/mistral/azure/ocr`, whichever of the
resource's Azure host names the endpoint uses), addressed to the OCR deployment, with the PDF as a
base64 data URL and the 0-based list of the pages to read; image data is not requested back.
Authentication is keyless, an Entra ID bearer token for
`https://cognitiveservices.azure.com/.default` from `DefaultAzureCredential`, as for the teach
deployment. The wall clock of the call - token acquisition, DNS, connect, TLS, sending and
reading the last byte - is bounded by `asyncio.timeout` on top of the HTTP client's own
timeout, and nothing is retried. The HTTP and Azure loggers are held at WARNING and filtered,
so neither the document nor a token reaches a log.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.clients.foundry_llm_client import entra_token_provider
from app.clients.llm_log_redaction import protect_loggers
from app.clients.ocr_client import OcrProviderError, OcrRequest, OcrResult, OcrTimeout
from app.config import PagePrice

logger = logging.getLogger(__name__)

PROVIDER = "azure_foundry"
OCR_ROUTE = "/providers/mistral/azure/ocr"
MAX_LATENCY_MS = 300_000
FOUNDRY_HOST_SUFFIXES = (
    ".cognitiveservices.azure.com",
    ".services.ai.azure.com",
    ".openai.azure.com",
)

_REDACTING_FILTER = protect_loggers(("azure", "msal", "httpx", "httpcore", "urllib3"))


class FoundryOcrClient:
    provider = PROVIDER

    def __init__(self, endpoint: str, deployment: str, model: str, price: PagePrice) -> None:
        self.model = model
        self.price = price
        self._url = ocr_url(endpoint)
        self._deployment = deployment
        self._token = entra_token_provider()

    def __repr__(self) -> str:
        return f"FoundryOcrClient(deployment={self._deployment!r}, model={self.model!r})"

    async def recognise(self, request: OcrRequest) -> OcrResult:
        started = time.monotonic()
        body = {
            "model": self._deployment,
            "document": {
                "type": "document_url",
                "document_url": "data:application/pdf;base64,"
                + base64.b64encode(request.pdf).decode("ascii"),
            },
            "pages": [page - 1 for page in request.pages],
            "include_image_base64": False,
        }
        limit = request.timeout_seconds
        try:
            async with asyncio.timeout(limit):
                try:
                    token = await self._token()
                except Exception as exc:
                    # The credential chain's messages name environment and account details.
                    logger.warning("OCR call failed: no Entra ID token was acquired")
                    raise OcrProviderError("credential", latency_ms=_elapsed(started)) from exc
                async with httpx.AsyncClient(timeout=httpx.Timeout(limit)) as client:
                    response = await client.post(
                        self._url, json=body, headers={"Authorization": f"Bearer {token}"}
                    )
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise OcrTimeout("timeout", latency_ms=_elapsed(started)) from exc
        except httpx.HTTPError as exc:
            logger.warning("OCR call failed to connect: %s", type(exc).__name__)
            raise OcrProviderError("connection", latency_ms=_elapsed(started)) from exc
        latency = _elapsed(started)
        if response.status_code != 200:
            logger.warning("OCR call refused with status %s", response.status_code)
            raise OcrProviderError("status", latency_ms=latency)
        try:
            return _result(response.json(), request.pages, latency)
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("OCR answer could not be read")
            raise OcrProviderError("invalid_output", latency_ms=latency) from exc


def ocr_url(endpoint: str) -> str:
    """The Mistral OCR URL of a Foundry resource: its `services.ai.azure.com` host when the
    endpoint names the resource by one of its Azure host names, else the endpoint itself."""
    host = urlsplit(endpoint.strip()).hostname or ""
    for suffix in FOUNDRY_HOST_SUFFIXES:
        if host.endswith(suffix) and len(host) > len(suffix):
            return f"https://{host[: -len(suffix)]}.services.ai.azure.com{OCR_ROUTE}"
    return endpoint.rstrip("/") + OCR_ROUTE


def _result(answer: dict[str, Any], asked: list[int], latency_ms: int) -> OcrResult:
    """The recognised pages the call asked for; any other page in the answer is ignored."""
    wanted = set(asked)
    pages: dict[int, str] = {}
    for page in answer["pages"]:
        number = int(page["index"]) + 1
        if number in wanted:
            markdown = page.get("markdown") or ""
            if not isinstance(markdown, str):
                raise TypeError("markdown is not text")
            pages[number] = markdown
    usage = answer.get("usage_info") or {}
    processed = int(usage.get("pages_processed", len(pages)))
    return OcrResult(pages, max(0, processed), 0, 0, latency_ms)


def _elapsed(started: float) -> int:
    return min(MAX_LATENCY_MS, max(0, int((time.monotonic() - started) * 1000)))
