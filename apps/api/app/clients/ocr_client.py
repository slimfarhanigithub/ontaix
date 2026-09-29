"""Provider-neutral OCR adapter: PDF bytes and a page list in, recognised text per page out.

The rest of the API sees only this module. A request carries a PDF of the pages to recognise
and nothing else of the document, their 1-based numbers in that PDF, and the wall clock of the
call; the result carries Markdown text per page, the
pages the provider processed, the token counts it reported (often 0) and the latency. A timeout
or a provider failure raises `OcrTimeout` or `OcrProviderError`. No provider type, SDK class or
credential leaves the implementation modules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.config import PagePrice, Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrRequest:
    # The image-only pages alone, never the uploaded document.
    pdf: bytes
    # 1-based page numbers in `pdf`, ascending.
    pages: list[int]
    timeout_seconds: float


@dataclass(frozen=True)
class OcrResult:
    # 1-based page number to the page's text as Markdown.
    pages: dict[int, str]
    pages_processed: int
    input_tokens: int
    output_tokens: int
    latency_ms: int


class OcrCallError(Exception):
    """A call that produced no usable result; carries what the provider reported."""

    def __init__(self, reason: str, pages_processed: int = 0, latency_ms: int = 0) -> None:
        super().__init__(reason)
        self.pages_processed = pages_processed
        self.latency_ms = latency_ms


class OcrTimeout(OcrCallError):
    """No complete result within the wall-clock timeout."""


class OcrProviderError(OcrCallError):
    """The provider refused, failed or answered something that is not a result."""


class OcrClient(Protocol):
    provider: str
    model: str
    price: PagePrice

    async def recognise(self, request: OcrRequest) -> OcrResult: ...


_override: OcrClient | None = None
_override_set = False
_cached: tuple[tuple[object, ...], OcrClient] | None = None


def get_ocr_client() -> OcrClient | None:
    """The configured client, or None when OCR has no endpoint or its model no page price."""
    if _override_set:
        return _override
    return _configured(get_settings())


def set_ocr_client(client: OcrClient | None) -> None:
    """Replace the configured client (tests); `reset_ocr_client` restores configuration."""
    global _override, _override_set
    _override, _override_set = client, True


def reset_ocr_client() -> None:
    global _override, _override_set
    _override, _override_set = None, False


def check_ocr_configuration(settings: Settings) -> None:
    """Warns at start-up when OCR has an endpoint but its model has no page price: OCR is then
    not configured and a PDF that needs it is refused with `503`."""
    if settings.ocr_endpoint_or_default() is None:
        return
    if not isinstance(settings.llm_price_table.get(settings.ocr_model_name()), PagePrice):
        logger.warning(
            "OCR is not configured: ONTAIX_LLM_PRICE_TABLE has no eurPerPage price for the OCR "
            "model %r",
            settings.ocr_model_name(),
        )


def _configured(settings: Settings) -> OcrClient | None:
    global _cached
    endpoint = settings.ocr_endpoint_or_default()
    model = settings.ocr_model_name()
    price = settings.llm_price_table.get(model)
    if endpoint is None or not isinstance(price, PagePrice):
        return None
    fingerprint: tuple[object, ...] = (endpoint, settings.ocr_deployment, model, price)
    if _cached is None or _cached[0] != fingerprint:
        from app.clients.foundry_ocr_client import FoundryOcrClient

        _cached = (fingerprint, FoundryOcrClient(endpoint, settings.ocr_deployment, model, price))
    return _cached[1]
