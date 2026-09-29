"""Isolation of untrusted files: the child process has no network and a memory cap, OCR receives
only the image-only pages, JSON nesting is bounded, and archives stop at their byte caps."""

from __future__ import annotations

import io
import socket
import sys
import zipfile

import httpx
import pytest
from pypdf import PdfReader

from app.clients.ocr_client import set_ocr_client
from app.config import get_settings
from app.services import child_process_service
from app.utilities import ooxml_archive
from app.utilities.document_errors import DocumentTooLargeError
from app.utilities.ooxml_archive import OoxmlArchive
from tests import child_targets
from tests.conftest import TenantFixture
from tests.test_import_formats import FakeOcr
from tests.test_imports import pdf, upload
from tests.test_ontology_import import FIXTURES
from tests.test_ontology_import import upload as upload_ontology

pytestmark = pytest.mark.asyncio(loop_scope="session")

MIB = 1024 * 1024


async def test_the_child_cannot_reach_the_network() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        outcomes = await child_process_service.run(
            child_targets.try_connect, (port,), 30, "a test job"
        )
    finally:
        listener.close()

    assert outcomes == ["OSError"] * 4


@pytest.mark.skipif(sys.platform == "win32", reason="RLIMIT_AS exists on Linux only")
async def test_the_child_memory_cap_refuses_a_large_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "extraction_memory_limit_bytes", 256 * MIB)
    with pytest.raises(DocumentTooLargeError, match="memory"):
        await child_process_service.run(child_targets.allocate, (512,), 30, "a test job")


async def test_running_out_of_memory_in_the_child_is_too_large() -> None:
    with pytest.raises(DocumentTooLargeError, match="memory"):
        await child_process_service.run(child_targets.run_out_of_memory, (), 30, "a test job")


async def test_ocr_receives_only_the_image_only_pages_and_maps_them_back(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    fake = FakeOcr(
        {
            1: "The first scanned page names every machine.",
            2: "The second scanned page lists spare parts.",
        }
    )
    set_ocr_client(fake)
    data = pdf(
        ["The text page tells the whole story.", "", "Another text page of the handbook.", ""]
    )

    response = await upload(client, tenant.builder, "mixed.pdf", data, "application/pdf")

    assert response.status_code == 200, response.text
    [request] = fake.requests
    sent = PdfReader(io.BytesIO(request.pdf))
    assert len(sent.pages) == 2 and request.pages == [1, 2]
    assert "text page" not in "".join(p.extract_text() or "" for p in sent.pages)
    assert request.pdf != data
    body = response.json()
    assert list(zip(body["sentences"], [p["index"] for p in body["positions"]], strict=True)) == [
        ("The text page tells the whole story.", 1),
        ("The first scanned page names every machine.", 2),
        ("Another text page of the handbook.", 3),
        ("The second scanned page lists spare parts.", 4),
    ]


async def test_deeply_nested_json_ld_is_refused_not_a_server_error(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    nested = b'{"@context": {}, "@graph": ' + b"[" * 200_000 + b"]" * 200_000 + b"}"

    response = await upload_ontology(client, tenant, "deep.jsonld", nested)

    assert response.status_code == 422, response.text
    assert "nests" in response.json()["detail"]


async def test_an_owl_xml_file_with_a_dtd_or_entities_is_refused(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await upload_ontology(client, tenant, "entities.owx")

    assert response.status_code == 415, response.text
    assert (FIXTURES / "entities.owx").read_bytes().count(b"<!ENTITY") == 2


async def test_an_archive_member_stops_at_50_mib_inflated(monkeypatch: pytest.MonkeyPatch) -> None:
    # The ratio check is lifted so the byte cap is what stops the read.
    monkeypatch.setattr(ooxml_archive, "MAX_COMPRESSION_RATIO", 10**9)
    data = _zipped({"big.xml": b"\0" * (51 * MIB)})
    with OoxmlArchive(data) as archive, pytest.raises(DocumentTooLargeError, match="50 MiB"):
        archive.read("big.xml")


async def test_an_archive_stops_at_200_mib_inflated_in_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ooxml_archive, "MAX_COMPRESSION_RATIO", 10**9)
    chunk = b"\0" * (45 * MIB)
    data = _zipped({f"part{i}.xml": chunk for i in range(5)})
    with OoxmlArchive(data) as archive, pytest.raises(DocumentTooLargeError, match="200 MiB"):
        for i in range(5):
            archive.read(f"part{i}.xml")


def _zipped(parts: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return out.getvalue()
