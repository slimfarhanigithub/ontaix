"""The Foundry OCR client against a mocked HTTP transport: request shape, result and failures.

The request shape (route, body fields, 0-based page list) follows the provider's published
Mistral OCR API on Azure AI Foundry; it is checked here against a mock only.
"""

from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from app.clients import foundry_ocr_client
from app.clients.foundry_ocr_client import FoundryOcrClient
from app.clients.ocr_client import OcrProviderError, OcrRequest, OcrTimeout, get_ocr_client
from app.config import PagePrice, Settings

pytestmark = pytest.mark.asyncio(loop_scope="session")

PRICE = PagePrice(eurPerPage="0.001")
PDF = b"%PDF-1.4 scanned"
REAL_ASYNC_CLIENT = httpx.AsyncClient


def client_with(
    monkeypatch: pytest.MonkeyPatch, handler, seen: list[httpx.Request]
) -> FoundryOcrClient:
    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        foundry_ocr_client.httpx,
        "AsyncClient",
        lambda **kw: REAL_ASYNC_CLIENT(transport=httpx.MockTransport(recording), **kw),
    )

    async def token() -> str:
        return "test-token"

    monkeypatch.setattr(foundry_ocr_client, "entra_token_provider", lambda: token)
    return FoundryOcrClient(
        "https://ocr.example.test/", "mistral-document-ai", "mistral-ocr", PRICE
    )


async def test_one_call_sends_the_pdf_and_the_zero_based_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[httpx.Request] = []
    answer = {
        "pages": [
            {"index": 0, "markdown": "Page one text"},
            {"index": 2, "markdown": "Page three text"},
            {"index": 5, "markdown": "Not asked"},
        ],
        "usage_info": {"pages_processed": 2},
    }
    client = client_with(monkeypatch, lambda _: httpx.Response(200, json=answer), seen)

    result = await client.recognise(OcrRequest(PDF, [1, 3], 10))

    [request] = seen
    assert str(request.url) == "https://ocr.example.test/providers/mistral/azure/ocr"
    assert request.headers["Authorization"] == "Bearer test-token"
    body = json.loads(request.content)
    assert body == {
        "model": "mistral-document-ai",
        "document": {
            "type": "document_url",
            "document_url": "data:application/pdf;base64," + base64.b64encode(PDF).decode(),
        },
        "pages": [0, 2],
        "include_image_base64": False,
    }
    assert result.pages == {1: "Page one text", 3: "Page three text"}
    assert result.pages_processed == 2


async def test_the_route_uses_the_resource_ai_services_host() -> None:
    from app.clients.foundry_ocr_client import ocr_url

    expected = "https://ontaix-dev.services.ai.azure.com/providers/mistral/azure/ocr"
    assert ocr_url("https://ontaix-dev.cognitiveservices.azure.com/") == expected
    assert ocr_url("https://ontaix-dev.services.ai.azure.com") == expected


async def test_a_refused_or_unreadable_answer_is_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refused = client_with(monkeypatch, lambda _: httpx.Response(429, json={}), [])
    with pytest.raises(OcrProviderError):
        await refused.recognise(OcrRequest(PDF, [1], 10))
    garbled = client_with(monkeypatch, lambda _: httpx.Response(200, text="not json"), [])
    with pytest.raises(OcrProviderError):
        await garbled.recognise(OcrRequest(PDF, [1], 10))


async def test_the_wall_clock_bounds_the_call(monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_with(monkeypatch, lambda _: httpx.Response(200, json={"pages": []}), [])

    async def slow() -> str:
        await asyncio.sleep(1)
        return "late-token"

    client._token = slow
    with pytest.raises(OcrTimeout):
        await client.recognise(OcrRequest(PDF, [1], 0.05))


async def test_ocr_is_configured_only_with_an_endpoint_and_a_page_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.clients import ocr_client

    ocr_client.reset_ocr_client()
    monkeypatch.setattr(foundry_ocr_client, "entra_token_provider", lambda: None)
    for settings, configured in (
        (Settings(_env_file=None), False),
        (Settings(_env_file=None, foundry_endpoint="https://f.example.test"), False),
        (
            Settings(
                _env_file=None,
                foundry_endpoint="https://f.example.test",
                llm_price_table={"mistral-document-ai": {"eurPerPage": 0.001}},
            ),
            True,
        ),
        (
            Settings(
                _env_file=None,
                ocr_endpoint="https://o.example.test",
                ocr_model="mistral-ocr-4-0",
                llm_price_table={"mistral-ocr-4-0": {"inputEurPerMTok": 1, "outputEurPerMTok": 1}},
            ),
            False,
        ),
    ):
        monkeypatch.setattr(ocr_client, "get_settings", lambda s=settings: s)
        assert (get_ocr_client() is not None) is configured
