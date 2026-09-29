"""POST /import/sentences and the drafts and parses that cite a stored import sentence."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.clients import db_client
from app.models.storage.document_import import DocumentImport
from app.models.storage.document_import_sentence import DocumentImportSentence
from app.services import import_service, rate_limit_service
from app.services.rate_limit_service import Budget
from tests.conftest import Persona, TenantFixture
from tests.test_teach import set_settings

pytestmark = pytest.mark.asyncio(loop_scope="session")

TXT = b"A plant has machines. Machines have sensors!\nok.\n"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def docx(paragraphs: list[str], doctype: str = "") -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        + doctype
        + '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        + f"<w:body>{body}</w:body></w:document>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return out.getvalue()


def pdf(pages: list[str]) -> bytes:
    """A minimal PDF with one line of Helvetica text per page."""
    objects: list[bytes] = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    font = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
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


async def upload(
    client: httpx.AsyncClient,
    persona: Persona,
    name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> httpx.Response:
    return await client.post(
        "/import/sentences", files={"file": (name, data, content_type)}, headers=persona.headers
    )


async def cite(
    client: httpx.AsyncClient, tenant: TenantFixture, persona: Persona, import_id: str, index: int
) -> httpx.Response:
    return await client.post(
        "/teach/parse",
        json={
            "companyId": str(tenant.company_id),
            "importRef": {"importId": import_id, "sentenceIndex": index},
        },
        headers=persona.headers,
    )


async def test_text_import_is_stored_and_its_sentences_become_document_proposals(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await upload(client, tenant.builder, "C:\\notes\\plant notes.txt", TXT, "text/plain")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["fileName"] == "plant notes.txt"
    assert body["sentences"] == ["A plant has machines.", "Machines have sensors!"]
    assert body["positions"] == [None, None]
    assert body["origin"] == "document"
    assert body["originDetail"] == {"fileName": "plant notes.txt", "mediaType": "text/plain"}
    async with db_client.get_session_factory()() as s:
        row = await s.get(DocumentImport, uuid.UUID(body["importId"]))
        assert row is not None and len(row.sha256) == 32 and row.sentence_count == 2
        assert row.expires_at - row.created_at == timedelta(hours=1)

    parsed = await cite(client, tenant, tenant.builder, body["importId"], 0)
    assert parsed.status_code == 200, parsed.text
    result = parsed.json()
    detail = {"fileName": "plant notes.txt", "mediaType": "text/plain", "sentenceIndex": 0}
    assert result["origin"] == "document" and result["originDetail"] == detail
    ref = {"importId": body["importId"], "sentenceIndex": 0}
    assert all(d["importRef"] == ref for d in result["drafts"])

    created = await client.post(
        "/proposals/batch", json={"drafts": result["drafts"]}, headers=tenant.builder.headers
    )
    assert created.status_code == 202, created.text
    assert [(p["origin"], p["originDetail"]) for p in created.json()] == [("document", detail)] * 2

    approved = await client.post(
        f"/proposals/{created.json()[0]['id']}/approve", headers=tenant.governor.headers
    )
    assert approved.json()["audit"]["origin"] == "document"
    audit = (await client.get("/audit?pageSize=200", headers=tenant.governor.headers)).json()
    assert {e["origin"] for e in audit["items"] if e["proposalId"]} == {"document"}
    assert all(e["origin"] is None for e in audit["items"] if not e["proposalId"])

    again = await client.post(
        "/proposals/batch",
        json={"importRef": ref, "drafts": [{**result["drafts"][0], "label": "Site"}]},
        headers=tenant.builder.headers,
    )
    assert again.status_code == 409 and again.json()["code"] == "import_sentence_used"


async def test_a_cited_sentence_is_parsed_three_times_at_most(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    import_id = (await upload(client, tenant.builder, "a.txt", TXT)).json()["importId"]

    codes = [(await cite(client, tenant, tenant.builder, import_id, 1)).status_code for _ in "1234"]
    fourth = await cite(client, tenant, tenant.builder, import_id, 1)
    missing = await cite(client, tenant, tenant.builder, import_id, 7)

    assert codes == [200, 200, 200, 409]
    assert fourth.json()["code"] == "import_sentence_used"
    assert missing.status_code == 404


async def test_csv_rows_become_sentences(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    data = b"subject;verb;object\nPlant;has;machines\nWarehouse,stores,materials\n"

    body = (await upload(client, tenant.builder, "model.csv", data)).json()

    assert body["originDetail"]["mediaType"] == "text/csv"
    assert body["sentences"] == [
        "subject verb object.",
        "Plant has machines.",
        "Warehouse stores materials.",
    ]


async def test_word_document_keeps_paragraph_positions(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    data = docx(["Title", "A plant has machines. Lines have shifts.", "A warehouse holds stock."])

    body = (await upload(client, tenant.builder, "model.docx", data)).json()

    assert body["originDetail"]["mediaType"] == DOCX_TYPE
    assert body["sentences"] == [
        "A plant has machines.",
        "Lines have shifts.",
        "A warehouse holds stock.",
    ]
    assert body["positions"] == [
        {"unit": "paragraph", "index": 2},
        {"unit": "paragraph", "index": 2},
        {"unit": "paragraph", "index": 3},
    ]
    parsed = (await cite(client, tenant, tenant.builder, body["importId"], 2)).json()
    assert parsed["originDetail"]["position"] == {"unit": "paragraph", "index": 3}


async def test_word_document_with_a_dtd_is_refused(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    data = docx(["A plant has machines."], '<!DOCTYPE w:document [<!ENTITY x "boom">]>')

    response = await upload(client, tenant.builder, "evil.docx", data)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


async def test_pdf_keeps_page_positions(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    data = pdf(["A plant has machines.", "A warehouse holds stock."])

    response = await upload(client, tenant.builder, "model.pdf", data)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sentences"] == ["A plant has machines.", "A warehouse holds stock."]
    assert body["positions"] == [{"unit": "page", "index": 1}, {"unit": "page", "index": 2}]


async def test_refusals_of_the_upload(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    unsupported = await upload(client, tenant.builder, "run.exe", b"MZ")
    bad_name = await upload(client, tenant.builder, "a:b.txt", TXT)
    bidi = await upload(client, tenant.builder, "evil\u202etxt.exe.txt", TXT)
    too_large = await upload(client, tenant.builder, "big.txt", b"a" * (10 * 1024 * 1024 + 1))

    assert unsupported.status_code == 415
    assert unsupported.json()["code"] == "unsupported_media_type"
    assert bad_name.status_code == 422 and bidi.status_code == 422
    assert too_large.status_code == 413
    assert too_large.json()["code"] == "payload_too_large"


async def test_an_import_belongs_to_its_actor_and_expires(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    import_id = (await upload(client, tenant.builder, "a.txt", TXT)).json()["importId"]

    other_actor = await cite(client, tenant, tenant.owner, import_id, 0)
    async with db_client.get_session_factory()() as s:
        await s.execute(
            update(DocumentImport)
            .where(DocumentImport.id == uuid.UUID(import_id))
            .values(
                created_at=DocumentImport.created_at - timedelta(hours=2),
                expires_at=DocumentImport.expires_at - timedelta(hours=2),
            )
        )
        await s.commit()
    expired = await cite(client, tenant, tenant.builder, import_id, 0)

    assert other_actor.status_code == 404
    assert expired.status_code == 410
    assert expired.json()["code"] == "import_expired"


async def test_import_docs_off_refuses_imports_and_citations(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    import_id = (await upload(client, tenant.builder, "a.txt", TXT)).json()["importId"]
    await set_settings(tenant, import_docs=False)

    new_import = await upload(client, tenant.builder, "b.txt", TXT)
    parsed = await cite(client, tenant, tenant.builder, import_id, 0)
    drafted = await client.post(
        "/proposals",
        json={
            "type": "concept",
            "companyId": str(tenant.company_id),
            "parentId": str(tenant.root_id),
            "label": "Plant",
            "domainKey": "production",
            "importRef": {"importId": import_id, "sentenceIndex": 0},
        },
        headers=tenant.builder.headers,
    )

    for response in (new_import, parsed, drafted):
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "channel_disabled"


async def test_resource_endpoints_refuse_an_import_ref(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    import_id = (await upload(client, tenant.builder, "a.txt", TXT)).json()["importId"]

    response = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": str(tenant.company_id),
            "parentId": str(tenant.root_id),
            "label": "Plant",
            "domainKey": "production",
            "importRef": {"importId": import_id, "sentenceIndex": 0},
        },
        headers=tenant.builder.headers,
    )

    assert response.status_code == 422


async def test_the_import_budget_is_charged_before_the_upload_is_read(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(rate_limit_service.UNITS_PER_WINDOW, Budget.IMPORT, 1)
    empty = await upload(client, tenant.builder, "empty.txt", b"no")
    refused = await upload(client, tenant.builder, "a.txt", TXT)

    assert empty.status_code == 200 and empty.json()["sentences"] == []
    assert refused.status_code == 429
    assert refused.json()["code"] == "rate_limited"
    assert int(refused.headers["Retry-After"]) > 0


async def test_the_parse_budget_must_cover_every_sentence(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(rate_limit_service.UNITS_PER_WINDOW, Budget.PARSE, 1)
    refused = await upload(client, tenant.builder, "a.txt", TXT)

    assert refused.status_code == 429
    async with db_client.get_session_factory()() as s:
        stored = await s.scalars(
            select(DocumentImport).where(DocumentImport.tenant_id == tenant.tenant_id)
        )
        assert stored.all() == []


async def test_purge_deletes_imports_a_day_past_expiry(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
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
    async with db_client.get_session_factory()() as s:
        assert await import_service.purge_expired(s) >= 1
        await s.commit()
    async with db_client.get_session_factory()() as s:
        assert await s.get(DocumentImport, import_id) is None
        left = await s.scalars(
            select(DocumentImportSentence).where(DocumentImportSentence.import_id == import_id)
        )
        assert left.all() == []
