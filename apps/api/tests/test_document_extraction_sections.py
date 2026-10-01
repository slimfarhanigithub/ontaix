"""Pass 2 of a whole-document extraction: intents read by their fields, chunks read at once.

Recorded model answers only; no test reaches a provider.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.clients.llm_client import LlmAnswer, LlmRequest
from app.config import get_settings
from app.services import document_extraction_runner_service
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_document_extraction import OUTLINE, imported, start

pytestmark = pytest.mark.asyncio(loop_scope="session")


def intent(subject: dict, obj: dict, sentence: int, span: str, **fields: object) -> dict:
    return {
        "kind": "rel",
        "subject": subject,
        "object": obj,
        "confidence": 0.85,
        "sentenceIndex": sentence,
        "span": span,
        **fields,
    }


MIXED_SECTIONS = json.dumps(
    {
        "pass": "section",
        "intents": [
            # A spec whose action says `is a`: a specialisation, the action dropped.
            intent(
                {"newLabel": "Robots"},
                {"handle": "o2"},
                2,
                "uses robots",
                kind="spec",
                action="is a",
            ),
            # A spec with another action: a relation with that action.
            intent(
                {"handle": "o2"},
                {"newLabel": "Coating"},
                2,
                "apply the coating",
                kind="spec",
                action="applies",
            ),
            # A rel with a rule: the rule is dropped.
            intent(
                {"newLabel": "Quality inspectors"},
                {"newLabel": "Coating"},
                3,
                "Quality inspectors check every coating",
                action="check",
                rule="after drying",
            ),
            # A rel without an action is not understood; the chunk is still read.
            intent({"handle": "o1"}, {"handle": "o3"}, 1, "drying oven"),
        ],
        "unresolved": [],
    }
)


async def finished(client: httpx.AsyncClient, tenant: TenantFixture, job_id: str) -> dict:
    status = await client.get(f"/extractions/{job_id}", headers=tenant.builder.headers)
    assert status.status_code == 200, status.text
    return status.json()


async def test_section_intents_whose_fields_disagree_with_their_kind_are_read_not_refused(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    import_id = await imported(client, tenant)
    started = await start(client, tenant, import_id)
    assert started.status_code == 202, started.text
    fake_llm.answer(OUTLINE, MIXED_SECTIONS)

    assert await document_extraction_runner_service.run_once() is True

    job = await finished(client, tenant, started.json()["id"])
    assert (job["state"], job["degraded"]) == ("succeeded", False)
    result = await client.get(f"/extractions/{job['id']}/result", headers=tenant.builder.headers)
    body = result.json()
    drafts = [
        (d["type"], d["label"], d.get("parentLabel"), d.get("action")) for d in body["drafts"]
    ]
    assert drafts == [
        ("concept", "Paint shop", None, "runs"),
        ("concept", "Spray booth", "Paint shop", "includes"),
        ("concept", "Drying oven", "Paint shop", "includes"),
        ("spec", "Robots", "Spray booth", None),
        ("concept", "Coating", "Spray booth", "applies"),
        ("concept", "Quality inspectors", "Coating", "check"),
    ]
    assert body["drafts"][-1]["reverse"] is True
    assert [u["reason"] for u in body["unresolved"] if u.get("chunk") == 0][-1:] == [
        "not_understood"
    ]


class _SlowFake(FakeLlmClient):
    """The fake with a pause per call, counting how many calls run at once."""

    def __init__(self) -> None:
        super().__init__()
        self.in_flight = 0
        self.most_at_once = 0

    async def complete(self, request: LlmRequest) -> LlmAnswer:
        self.in_flight += 1
        self.most_at_once = max(self.most_at_once, self.in_flight)
        try:
            await asyncio.sleep(0.05)
            return await super().complete(request)
        finally:
            self.in_flight -= 1


def sections_for(data: dict) -> str:
    """A section answer for the chunk a request carries: one intent per sentence of it, so
    the answer fits whichever chunk's call reads it."""
    return json.dumps(
        {
            "pass": "section",
            "intents": [
                intent(
                    {"handle": "c0"},
                    {"newLabel": f"Item {s['index']}"},
                    s["index"],
                    f"item {s['index']}",
                    action="has",
                )
                for s in data["sentences"]
            ],
            "unresolved": [],
        }
    )


async def test_section_chunks_are_read_at_once_and_join_the_outline_in_chunk_order(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.clients.llm_client import set_llm_client
    from tests.test_imports import upload

    settings = get_settings()
    monkeypatch.setattr(settings, "document_extraction_chunk_chars", 60)
    monkeypatch.setattr(settings, "document_extraction_concurrency", 2)
    document = "\n".join(f"Sentence number {i} names item {i} here." for i in range(6))
    response = await upload(client, tenant.builder, "items.txt", document.encode(), "text/plain")
    assert response.status_code == 200, response.text
    import_id = response.json()["importId"]
    started = await start(client, tenant, import_id)
    assert started.status_code == 202, started.text
    chunks = started.json()["chunks"]
    assert chunks >= 3
    fake = _SlowFake()
    set_llm_client(fake)
    empty_outline = json.dumps({"pass": "outline", "nodes": []})
    fake.answer(*[empty_outline] * chunks)
    # Chunks of 60 characters over 36-character sentences hold one sentence each.
    fake.answer(*[sections_for] * chunks)

    assert await document_extraction_runner_service.run_once() is True

    job = await finished(client, tenant, started.json()["id"])
    assert (job["state"], job["sectionChunksDone"]) == ("succeeded", chunks)
    assert fake.most_at_once == 2
    result = await client.get(f"/extractions/{job['id']}/result", headers=tenant.builder.headers)
    labels = [d["label"] for d in result.json()["drafts"]]
    assert labels == [f"Item {i}" for i in range(chunks)]
