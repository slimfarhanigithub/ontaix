"""OCR for scanned PDFs: a protocol, a Mistral OCR client on Azure AI Foundry, and a fake.

The Azure client authenticates keylessly with a Microsoft Entra ID bearer token for the
Cognitive Services scope and posts the PDF inline as a base64 data URL. Document content and
tokens are never logged.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
MISTRAL_OCR_PATH = "/providers/mistral/azure/ocr"
DEFAULT_TIMEOUT_S = 180.0
_FOUNDRY_HOST_SUFFIXES = (
    ".cognitiveservices.azure.com",
    ".services.ai.azure.com",
    ".openai.azure.com",
)

TokenProvider = Callable[[], str]


@dataclass
class OcrResult:
    text: str
    pages: int
    latency_ms: int
    cost_eur: float


class OcrError(Exception):
    """The OCR service refused the document or answered with something unreadable."""


class OcrClient(Protocol):
    deployment: str

    async def ocr_pdf(self, data: bytes) -> OcrResult: ...


def mistral_ocr_url(foundry_endpoint: str) -> str:
    """The Mistral OCR URL of a Foundry resource, from its endpoint.

    `https://<resource>.cognitiveservices.azure.com` (or `.services.ai.azure.com`,
    `.openai.azure.com`) becomes
    `https://<resource>.services.ai.azure.com/providers/mistral/azure/ocr`.
    """
    host = urlsplit(foundry_endpoint.strip()).hostname or ""
    for suffix in _FOUNDRY_HOST_SUFFIXES:
        if host.endswith(suffix) and len(host) > len(suffix):
            resource = host[: -len(suffix)]
            return f"https://{resource}.services.ai.azure.com{MISTRAL_OCR_PATH}"
    raise ValueError(f"not an Azure AI Foundry endpoint: {foundry_endpoint!r}")


def mistral_ocr_body(deployment: str, data: bytes) -> dict[str, Any]:
    """The JSON body of one Mistral OCR request for a PDF sent inline."""
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "model": deployment,
        "document": {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{encoded}",
        },
        "include_image_base64": False,
    }


def parse_mistral_ocr_response(payload: Any) -> tuple[str, int]:
    """The page Markdown joined by blank lines, and the number of pages processed."""
    if not isinstance(payload, dict) or not isinstance(payload.get("pages"), list):
        raise OcrError("the OCR response has no pages")
    pages = payload["pages"]
    texts = [
        page["markdown"].strip()
        for page in pages
        if isinstance(page, dict) and isinstance(page.get("markdown"), str)
    ]
    usage = payload.get("usage_info")
    processed = usage.get("pages_processed") if isinstance(usage, dict) else None
    count = processed if isinstance(processed, int) and processed >= 0 else len(pages)
    return "\n\n".join(t for t in texts if t), count


class AzureMistralOcrClient:
    """Mistral OCR (`mistral-ocr-4-0`, `mistral-document-ai-2512`) deployed on Azure AI Foundry."""

    def __init__(
        self,
        *,
        url: str,
        deployment: str,
        price_eur_per_1000_pages: float,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        token_provider: TokenProvider | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url
        self.deployment = deployment
        self.price_eur_per_1000_pages = price_eur_per_1000_pages
        self.timeout_s = timeout_s
        self._token_provider = token_provider
        self._transport = transport

    @classmethod
    def from_foundry_endpoint(
        cls,
        foundry_endpoint: str,
        *,
        deployment: str,
        price_eur_per_1000_pages: float,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        token_provider: TokenProvider | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> AzureMistralOcrClient:
        return cls(
            url=mistral_ocr_url(foundry_endpoint),
            deployment=deployment,
            price_eur_per_1000_pages=price_eur_per_1000_pages,
            timeout_s=timeout_s,
            token_provider=token_provider,
            transport=transport,
        )

    async def ocr_pdf(self, data: bytes) -> OcrResult:
        token = await asyncio.to_thread(self._provider())
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = mistral_ocr_body(self.deployment, data)
        started = time.perf_counter()
        async with httpx.AsyncClient(transport=self._transport, timeout=self.timeout_s) as client:
            response = await client.post(self.url, json=body, headers=headers)
        latency_ms = round((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            logger.warning(
                "OCR deployment %s answered HTTP %s", self.deployment, response.status_code
            )
            raise OcrError(f"the OCR service answered HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OcrError("the OCR response is not JSON") from exc
        text, pages = parse_mistral_ocr_response(payload)
        logger.info("OCR deployment %s read %d pages in %d ms", self.deployment, pages, latency_ms)
        return OcrResult(
            text=text,
            pages=pages,
            latency_ms=latency_ms,
            cost_eur=pages * self.price_eur_per_1000_pages / 1000,
        )

    def _provider(self) -> TokenProvider:
        if self._token_provider is None:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            self._token_provider = get_bearer_token_provider(
                DefaultAzureCredential(), COGNITIVE_SERVICES_SCOPE
            )
        return self._token_provider


class FakeOcrClient:
    """Returns a fixed text for every PDF and records the bytes it was given."""

    def __init__(self, text: str, deployment: str = "fake-ocr") -> None:
        self.text = text
        self.deployment = deployment
        self.calls: list[bytes] = []

    async def ocr_pdf(self, data: bytes) -> OcrResult:
        self.calls.append(data)
        return OcrResult(text=self.text, pages=1, latency_ms=0, cost_eur=0.0)
