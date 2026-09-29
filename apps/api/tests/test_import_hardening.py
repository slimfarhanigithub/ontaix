"""Regression tests for hostile uploads and the budgets around imports and proposals.

Covers: extraction runs off the event loop in a child process bounded in time, DOCX element and
PDF decompression limits, a streamed upload refused while it is read, content sniffing, the
refused file-name characters, the proposal budget on resource endpoints, and the scheduled purge.
"""

from __future__ import annotations

import asyncio
import io
import time
import uuid
import zipfile
import zlib
from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import update

from app.clients import db_client
from app.config import get_settings
from app.main import app
from app.models.storage.document_import import DocumentImport
from app.services import extraction_service, import_service, rate_limit_service
from app.services.rate_limit_service import Budget
from app.utilities import document_text
from tests.conftest import TenantFixture
from tests.test_imports import DOCX_TYPE, TXT, pdf, upload

pytestmark = pytest.mark.asyncio(loop_scope="session")

WORD_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def docx_with_xml(xml: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", xml)
    return out.getvalue()


def pdf_with_stream(raw: bytes) -> bytes:
    """A one-page PDF whose content stream is `raw`, flate-compressed."""
    stream = zlib.compress(raw, 9)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % n + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    )
    return out.getvalue()


def concept(tenant: TenantFixture, label: str) -> dict:
    return {
        "type": "concept",
        "companyId": str(tenant.company_id),
        "parentId": str(tenant.root_id),
        "label": label,
        "domainKey": "production",
    }


async def test_many_empty_docx_elements_stop_at_the_element_cap() -> None:
    """Non-paragraph elements used to accumulate uncleared and cost a minute of CPU."""
    xml = f"<w:document {WORD_NS}><w:body>" + "<w:x/>" * 1_500_000 + "</w:body></w:document>"
    started = time.monotonic()
    with pytest.raises(document_text.DocumentTooLargeError):
        document_text.extract_sentences(docx_with_xml(xml), DOCX_TYPE)
    assert time.monotonic() - started < 20


async def test_docx_under_the_element_cap_still_reads_its_paragraphs() -> None:
    body = "<w:x/>" * 1000 + "<w:p><w:r><w:t>Machines have many sensors.</w:t></w:r></w:p>"
    xml = f"<w:document {WORD_NS}><w:body>{body}</w:body></w:document>"
    sentences, _, _ = document_text.extract_sentences(docx_with_xml(xml), DOCX_TYPE)
    assert [(s.text, s.unit, s.index) for s in sentences] == [
        ("Machines have many sensors.", "paragraph", 1)
    ]


async def test_a_pdf_decompressing_past_the_pypdf_limit_is_413_not_500(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await upload(
        client, tenant.builder, "bomb.pdf", pdf_with_stream(b" " * (200 * 1024 * 1024))
    )
    assert response.status_code == 413, response.text
    assert response.json()["code"] == "payload_too_large"


async def test_slow_extraction_is_stopped_at_the_time_limit_and_the_api_stays_responsive(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A small PDF with a very long run of text operators used to run for minutes on the loop."""
    monkeypatch.setattr(extraction_service, "EXTRACTION_TIMEOUT_SECONDS", 3.0)
    ops = b"BT /F1 12 Tf 72 720 Td (Machines have sensors.) Tj ET\n" * 400_000
    slow = pdf_with_stream(ops)
    started = time.monotonic()
    importing = asyncio.create_task(upload(client, tenant.builder, "slow.pdf", slow))
    await asyncio.sleep(0.5)
    health_times = []
    while not importing.done():
        t = time.monotonic()
        health = await client.get("/healthz")
        health_times.append(time.monotonic() - t)
        assert health.status_code == 200
        await asyncio.sleep(0.2)
    response = await importing
    assert response.status_code == 413, response.text
    assert time.monotonic() - started < 15
    assert health_times and max(health_times) < 1.0


async def test_a_chunked_upload_is_refused_while_it_streams(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no Content-Length the body used to be spooled whole before the size check."""
    called = False

    async def never(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(import_service, "import_sentences", never)
    sent = 0
    boundary = "XbX"

    async def body() -> AsyncIterator[bytes]:
        nonlocal sent
        yield (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="big.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
        ).encode()
        for _ in range(50):
            sent += 1
            yield b"a" * (1024 * 1024)
        yield f"\r\n--{boundary}--\r\n".encode()

    response = await client.post(
        "/import/sentences",
        content=body(),
        headers={
            **tenant.builder.headers,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    assert response.status_code == 413, response.text
    assert "content-length" not in response.request.headers
    assert not called
    assert sent <= 12


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("notes.txt", b"%PDF-1.4\nBT (Machines have sensors today) Tj ET"),
        # A UTF-16 byte order mark is read as UTF-16; these bytes are not UTF-8 and carry none.
        ("notes.txt", b"\xc3\x28 not UTF-8 at all, machines have sensors"),
        ("report.pdf", TXT),
        ("report.docx", TXT),
    ],
)
async def test_content_that_does_not_match_its_media_type_is_415(
    client: httpx.AsyncClient, tenant: TenantFixture, name: str, data: bytes
) -> None:
    response = await upload(client, tenant.builder, name, data)
    assert response.status_code == 415, response.text
    assert response.json()["code"] == "unsupported_media_type"


async def test_a_pdf_named_pdf_still_imports(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await upload(client, tenant.builder, "r.pdf", pdf(["Machines have sensors."]))
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("char", [" ", " ", "​", "‌", "‍"])
async def test_separators_and_zero_width_characters_are_refused_in_file_names(
    client: httpx.AsyncClient, tenant: TenantFixture, char: str
) -> None:
    response = await upload(client, tenant.builder, f"plan{char}s.txt", TXT)
    assert response.status_code == 422, response.text


async def test_resource_endpoints_spend_the_proposal_budget(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(rate_limit_service.UNITS_PER_WINDOW, Budget.PROPOSAL, 1)
    first = await client.post(
        "/concepts", json=concept(tenant, "Plant"), headers=tenant.builder.headers
    )
    second = await client.post(
        "/concepts", json=concept(tenant, "Line"), headers=tenant.builder.headers
    )
    third = await client.post(
        "/proposals", json=concept(tenant, "Shift"), headers=tenant.builder.headers
    )
    assert first.status_code == 202, first.text
    assert (second.status_code, third.status_code) == (429, 429)
    assert second.json()["code"] == "rate_limited"


async def test_a_company_with_its_starter_vocabulary_spends_thirteen_units(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(rate_limit_service.UNITS_PER_WINDOW, Budget.PROPOSAL, 12)
    refused = await client.post(
        "/companies",
        json={"name": f"Aurora {uuid.uuid4().hex[:6]}", "start": "starter_vocabulary"},
        headers=tenant.admin.headers,
    )
    monkeypatch.setitem(rate_limit_service.UNITS_PER_WINDOW, Budget.PROPOSAL, 13)
    added = await client.post(
        "/companies",
        json={"name": f"Aurora {uuid.uuid4().hex[:6]}", "start": "starter_vocabulary"},
        headers=tenant.admin.headers,
    )
    assert refused.status_code == 429, refused.text
    assert added.status_code == 201, added.text
    assert len(added.json()["proposals"]) == 13


async def test_the_app_lifespan_purges_expired_imports_on_a_schedule(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "import_purge_interval_seconds", 0.2)
    import_id = uuid.UUID((await upload(client, tenant.builder, "a.txt", TXT)).json()["importId"])
    async with db_client.get_session_factory()() as s:
        await s.execute(
            update(DocumentImport)
            .where(DocumentImport.id == import_id)
            .values(
                created_at=DocumentImport.created_at - timedelta(hours=26),
                expires_at=DocumentImport.expires_at - timedelta(hours=26),
            )
        )
        await s.commit()

    async def gone() -> bool:
        async with db_client.get_session_factory()() as s:
            return await s.get(DocumentImport, import_id) is None

    async with app.router.lifespan_context(app):
        tasks = [t for t in asyncio.all_tasks() if t.get_name() == "import-purge"]
        assert len(tasks) == 1
        for _ in range(50):
            if await gone():
                break
            await asyncio.sleep(0.1)
    assert await gone()
    assert tasks[0].cancelled()
    db_client.configure_engine(get_settings().database_url or "")


async def test_extractions_past_the_slot_limit_answer_503_busy_and_the_api_stays_responsive(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each import used to start its own child with no bound, across every user."""
    monkeypatch.setattr(get_settings(), "extraction_concurrency", 2)
    monkeypatch.setattr(extraction_service, "EXTRACTION_TIMEOUT_SECONDS", 3.0)
    slow = pdf_with_stream(b"BT /F1 12 Tf 72 720 Td (Machines have sensors.) Tj ET\n" * 400_000)
    imports = [
        asyncio.create_task(upload(client, tenant.builder, f"slow{i}.pdf", slow)) for i in range(5)
    ]
    await asyncio.sleep(0.5)
    health_times = []
    while not all(t.done() for t in imports):
        started = time.monotonic()
        assert (await client.get("/healthz")).status_code == 200
        health_times.append(time.monotonic() - started)
        await asyncio.sleep(0.2)
    responses = [await t for t in imports]
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [413, 413, 503, 503, 503], [r.text for r in responses]
    for busy in (r for r in responses if r.status_code == 503):
        assert busy.json()["code"] == "busy"
        assert int(busy.headers["Retry-After"]) > 0
    assert health_times and max(health_times) < 1.0
