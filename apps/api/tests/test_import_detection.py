"""POST /import/detect and the chosen reading of both imports, by the bytes of the file."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.utilities.import_detection import detect_import
from tests.conftest import TenantFixture
from tests.office_files import PPTX_TYPE, XLSX_TYPE, pptx, xlsx
from tests.test_imports import docx, pdf
from tests.test_teach import set_settings

pytestmark = pytest.mark.asyncio(loop_scope="session")

FIXTURES = Path(__file__).parent / "fixtures" / "ontology"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PROSE = b"The plant runs three lines. Each line has a maintenance crew."
TABLE_XLSX = xlsx([[["Customer", "City"], ["Aurora", "Lyon"]]])
HIERARCHY_XLSX = xlsx([[["Level 1", "Level 2"], ["Finance", "Invoices"]]])


async def detect(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    persona=None,
) -> httpx.Response:
    return await client.post(
        "/import/detect",
        files={"file": (name, data, content_type)},
        headers=(persona or tenant.builder).headers,
    )


@pytest.mark.parametrize(
    ("name", "fmt", "media_type"),
    [
        ("plant.ttl", "turtle", "text/plain"),
        ("plant.rdf", "rdf_xml", "text/plain"),
        ("plant.owx", "owl_xml", "text/plain"),
        ("plant.jsonld", "json_ld", "text/plain"),
        ("plant.nt", "n_triples", "text/plain"),
        ("plant.obo", "obo", "text/plain"),
        ("hierarchy.csv", "csv", "text/csv"),
        ("levels.csv", "csv", "text/csv"),
        # A DTD makes the XML unreadable here; the extension still names the format, and the
        # ontology import refuses the DTD.
        ("xxe.rdf", "rdf_xml", "text/plain"),
    ],
)
async def test_every_ontology_fixture_is_detected_as_its_format(
    client: httpx.AsyncClient, tenant: TenantFixture, name: str, fmt: str, media_type: str
) -> None:
    response = await detect(client, tenant, name, (FIXTURES / name).read_bytes())

    assert response.status_code == 200, response.text
    assert response.json() == {"kind": "ontology", "format": fmt, "mediaType": media_type}


@pytest.mark.parametrize(
    ("name", "data", "media_type"),
    [
        ("notes.txt", PROSE, "text/plain"),
        ("notes.md", b"# Plant\n\nThe plant runs three lines.", "text/markdown"),
        ("page.html", b"<!doctype html><p>The plant runs three lines.</p>", "text/html"),
        ("report.pdf", pdf(["The plant runs three lines."]), "application/pdf"),
        ("report.docx", docx(["The plant runs three lines."]), DOCX_TYPE),
        ("deck.pptx", pptx([(["The plant runs three lines."], [])]), PPTX_TYPE),
        ("table.xlsx", TABLE_XLSX, XLSX_TYPE),
        ("data.json", b'{"plant": "three lines"}', "application/json"),
    ],
)
async def test_documents_are_detected_with_their_media_type(
    client: httpx.AsyncClient, tenant: TenantFixture, name: str, data: bytes, media_type: str
) -> None:
    response = await detect(client, tenant, name, data)

    assert response.status_code == 200, response.text
    assert response.json() == {"kind": "document", "format": None, "mediaType": media_type}


async def test_a_csv_or_xlsx_is_an_ontology_only_with_a_hierarchy_header(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    table_csv = await detect(client, tenant, "table.csv", b"Customer,City\nAurora,Lyon\n")
    semicolons = await detect(client, tenant, "tree.csv", b"label;parent\nSales;\nOrders;Sales\n")
    hierarchy_xlsx = await detect(client, tenant, "tree.xlsx", HIERARCHY_XLSX, XLSX_TYPE)

    assert table_csv.json() == {"kind": "document", "format": None, "mediaType": "text/csv"}
    assert semicolons.json() == {"kind": "ontology", "format": "csv", "mediaType": "text/csv"}
    assert hierarchy_xlsx.json() == {"kind": "ontology", "format": "xlsx", "mediaType": XLSX_TYPE}


@pytest.mark.parametrize(
    ("name", "data", "kind", "fmt", "media_type"),
    [
        ("notes.txt", (FIXTURES / "plant.ttl").read_bytes(), "ontology", "turtle", "text/plain"),
        ("notes.md", (FIXTURES / "plant.rdf").read_bytes(), "ontology", "rdf_xml", "text/markdown"),
        ("plant.ttl", pdf(["The plant runs three lines."]), "document", None, "application/pdf"),
        ("plant.owl", docx(["The plant runs three lines."]), "document", None, DOCX_TYPE),
        ("plant.ttl", (FIXTURES / "plant.obo").read_bytes(), "ontology", "obo", "text/plain"),
        ("tree.txt", HIERARCHY_XLSX, "ontology", "xlsx", XLSX_TYPE),
    ],
)
async def test_the_content_wins_over_a_wrong_extension(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    name: str,
    data: bytes,
    kind: str,
    fmt: str | None,
    media_type: str,
) -> None:
    response = await detect(client, tenant, name, data)

    assert response.status_code == 200, response.text
    assert response.json() == {"kind": kind, "format": fmt, "mediaType": media_type}


async def test_text_with_no_ontology_signal_follows_its_extension_or_media_type() -> None:
    by_extension = detect_import("plant.ttl", None, PROSE)
    by_media_type = detect_import("plant", "text/turtle", PROSE)
    json_document = detect_import("data.json", None, b'{"a": 1}')

    assert (by_extension.kind, by_extension.format) == ("ontology", "turtle")
    assert (by_media_type.kind, by_media_type.format) == ("ontology", "turtle")
    assert (json_document.kind, json_document.format) == ("document", None)


async def test_detection_refusals(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    binary = await detect(client, tenant, "run.exe", b"\x00\x01\xff\xfe\x80")
    legacy = await detect(client, tenant, "old.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 8)
    bad_name = await detect(client, tenant, "a:b.txt", PROSE)
    outsider = await detect(client, tenant, "notes.txt", PROSE, persona=tenant.outsider)

    assert binary.status_code == 415 and binary.json()["code"] == "unsupported_media_type"
    assert legacy.status_code == 415
    assert bad_name.status_code == 422
    assert outsider.status_code == 403
    await set_settings(tenant, import_docs=False)
    disabled = await detect(client, tenant, "notes.txt", PROSE)
    assert disabled.status_code == 409 and disabled.json()["code"] == "channel_disabled"


async def test_a_chosen_format_reads_a_file_whatever_its_name(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    turtle = (FIXTURES / "plant.ttl").read_bytes()

    by_name = await _ontology(client, tenant, "notes.txt", turtle)
    chosen = await _ontology(client, tenant, "notes.txt", turtle, format="turtle")
    disagreeing = await _ontology(client, tenant, "notes.txt", turtle, format="rdf_xml")
    unknown = await _ontology(client, tenant, "notes.txt", turtle, format="owl")

    assert by_name.status_code == 415, by_name.text
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["format"] == "turtle"
    assert disagreeing.status_code == 415
    assert "chosen format" in disagreeing.json()["detail"]
    assert unknown.status_code == 422


async def test_a_chosen_media_type_reads_a_file_as_a_document_whatever_its_name(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    report = pdf(["The plant runs three lines."])

    by_name = await _document(client, tenant, "report.txt", report)
    chosen = await _document(client, tenant, "report.txt", report, "application/pdf")
    ontology_as_text = await _document(
        client, tenant, "plant.ttl", (FIXTURES / "plant.ttl").read_bytes(), "text/plain"
    )
    disagreeing = await _document(client, tenant, "report.txt", report, "text/plain")
    unknown = await _document(client, tenant, "report.txt", report, "image/png")

    assert by_name.status_code == 415, by_name.text
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["originDetail"]["mediaType"] == "application/pdf"
    assert ontology_as_text.status_code == 200, ontology_as_text.text
    assert ontology_as_text.json()["sentences"]
    assert disagreeing.status_code == 415
    assert unknown.status_code == 422


async def _ontology(
    client: httpx.AsyncClient, tenant: TenantFixture, name: str, data: bytes, **fields: str
) -> httpx.Response:
    return await client.post(
        "/ontology-imports",
        files={"file": (name, data, "application/octet-stream")},
        data={"companyId": str(tenant.company_id), **fields},
        headers=tenant.builder.headers,
    )


async def _document(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    name: str,
    data: bytes,
    media_type: str | None = None,
) -> httpx.Response:
    return await client.post(
        "/import/sentences",
        files={"file": (name, data, "application/octet-stream")},
        data={"mediaType": media_type} if media_type else {},
        headers=tenant.builder.headers,
    )
