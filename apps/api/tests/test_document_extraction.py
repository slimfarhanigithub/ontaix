"""Whole-document extraction jobs: start, the runner's two passes, the result and its tree of
proposals, against recorded model answers."""

from __future__ import annotations

import json
import time
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.clients import db_client
from app.clients.llm_client import set_llm_client
from app.repositories import document_extraction_job_repository
from app.services import document_extraction_runner_service
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_imports import upload

pytestmark = pytest.mark.asyncio(loop_scope="session")

DOCUMENT = (
    "Our company runs a paint shop for its customers.\n"
    "The paint shop includes a spray booth and a drying oven.\n"
    "The spray booth uses robots that apply the coating.\n"
    "Quality inspectors check every coating after drying.\n"
)


def node(key: str, parent: dict, label: str, action: str, sentence: int, span: str) -> dict:
    return {
        "key": key,
        "parent": parent,
        "label": label,
        "action": action,
        "role": "process",
        "confidence": 0.9,
        "sentenceIndex": sentence,
        "span": span,
    }


OUTLINE = json.dumps(
    {
        "pass": "outline",
        "nodes": [
            node("k1", {"handle": "c0"}, "Paint shop", "runs", 0, "paint shop"),
            node("k2", {"key": "k1"}, "Spray booth", "includes", 1, "spray booth"),
            node("k3", {"path": ["Paint shop"]}, "Drying oven", "includes", 1, "drying oven"),
            node("k4", {"key": "k2"}, "Magic wand", "has", 2, "robots"),
            node("k5", {"key": "k4"}, "Robots", "has", 2, "robots"),
            node("k6", {"path": ["Nowhere"]}, "Coating", "has", 2, "coating"),
        ],
    }
)


def intent(subject: dict, action: str, obj: dict, sentence: int, span: str) -> dict:
    return {
        "kind": "rel",
        "subject": subject,
        "object": obj,
        "action": action,
        "confidence": 0.85,
        "explanation": "Stated in the document.",
        "sentenceIndex": sentence,
        "span": span,
    }


SECTIONS = json.dumps(
    {
        "pass": "section",
        "intents": [
            intent({"handle": "o2"}, "uses", {"newLabel": "Robots"}, 2, "uses robots"),
            intent(
                {"newLabel": "Quality inspectors"},
                "check",
                {"newLabel": "Coating"},
                3,
                "Quality inspectors check every coating",
            ),
            intent({"handle": "o1"}, "includes", {"handle": "o2"}, 1, "includes a spray booth"),
        ],
        "unresolved": [{"sentenceIndex": 0, "reason": "not_a_statement"}],
    }
)


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def no_waiting_jobs(migrated_database: str) -> None:
    """The runner claims the oldest waiting job of any tenant, so each test starts with none."""
    async with db_client.get_platform_session_factory()() as s:
        await s.execute(
            text(
                "UPDATE ontaix.document_extraction_job SET state = 'cancelled', phase = NULL,"
                " finished_at = now(), lease_owner = NULL, lease_until = NULL"
                " WHERE state IN ('queued', 'running')"
            )
        )
        await s.commit()


async def rows(sql: str, **params: object) -> list[dict]:
    async with db_client.get_platform_session_factory()() as s:
        result = await s.execute(text(sql), params)
        return [dict(r._mapping) for r in result]


async def imported(client: httpx.AsyncClient, tenant: TenantFixture) -> str:
    response = await upload(client, tenant.builder, "plant.txt", DOCUMENT.encode(), "text/plain")
    assert response.status_code == 200, response.text
    return response.json()["importId"]


async def start(
    client: httpx.AsyncClient, tenant: TenantFixture, import_id: str, persona=None
) -> httpx.Response:
    return await client.post(
        f"/import/{import_id}/extraction",
        json={"companyId": str(tenant.company_id)},
        headers=(persona or tenant.builder).headers,
    )


async def test_a_document_becomes_one_grounded_tree_of_proposals(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    import_id = await imported(client, tenant)
    started = await start(client, tenant, import_id)
    assert started.status_code == 202, started.text
    job = started.json()
    assert (job["state"], job["chunks"], job["phase"]) == ("queued", 1, None)
    fake_llm.answer(OUTLINE, SECTIONS)

    assert await document_extraction_runner_service.run_once() is True

    status = await client.get(f"/extractions/{job['id']}", headers=tenant.builder.headers)
    job = status.json()
    assert (job["state"], job["failureReason"], job["draftCount"]) == ("succeeded", None, 6)
    assert (job["outlineChunksDone"], job["sectionChunksDone"], job["outlineNodes"]) == (1, 1, 3)
    assert job["tokensUsed"] > 0 and job["expiresAt"] and job["degraded"] is False

    outline_sent = fake_llm.context(0)
    assert outline_sent["pass"] == "outline" and outline_sent["outline"] == []
    assert outline_sent["candidates"][0]["handle"] == "c0"
    assert [s["index"] for s in outline_sent["sentences"]] == [0, 1, 2, 3]
    section_sent = fake_llm.context(1)
    assert [n["handle"] for n in section_sent["outline"]] == ["o1", "o2", "o3"]
    for request in fake_llm.requests:
        assert str(tenant.company_id) not in request.user
        assert str(tenant.root_id) not in request.user

    result = await client.get(f"/extractions/{job['id']}/result", headers=tenant.builder.headers)
    assert result.status_code == 200, result.text
    body = result.json()
    assert [(n["label"], n["depth"], n["parentIndex"]) for n in body["outline"]] == [
        ("Paint shop", 1, None),
        ("Spray booth", 2, 0),
        ("Drying oven", 2, 0),
    ]
    assert [(d["label"], d.get("parentLabel")) for d in body["drafts"]] == [
        ("Paint shop", None),
        ("Spray booth", "Paint shop"),
        ("Drying oven", "Paint shop"),
        ("Robots", "Spray booth"),
        ("Quality inspectors", None),
        ("Coating", "Quality inspectors"),
    ]
    assert body["drafts"][0]["parentId"] == str(tenant.root_id)
    assert [n["requires"] for n in body["notes"]] == [[], [0], [0], [1], [], [4]]
    assert [n["pass"] for n in body["notes"]] == ["outline"] * 3 + ["section"] * 3
    second = DOCUMENT.splitlines()[1]
    start_at = second.index("spray booth")
    assert body["notes"][1]["sourceSpan"] == {"start": start_at, "end": start_at + 11}
    assert "originDetail" not in body["notes"][0]
    assert {(u.get("label"), u["reason"]) for u in body["unresolved"]} == {
        (None, "ungrounded_label"),
        (None, "unknown_parent"),
        (None, "not_a_statement"),
    }

    events = await rows(
        "SELECT recipient_user_id, visibility, company_ids, payload FROM ontaix.outbox"
        " WHERE tenant_id = :t AND aggregate = 'extraction' ORDER BY id",
        t=tenant.tenant_id,
    )
    assert [e["payload"]["extraction"]["state"] for e in events][0] == "queued"
    assert events[-1]["payload"]["extraction"]["state"] == "succeeded"
    assert {e["recipient_user_id"] for e in events} == {tenant.builder.user_id}
    assert all(e["company_ids"] == [tenant.company_id] for e in events)
    assert "Paint" not in json.dumps([e["payload"] for e in events])

    proposed = await client.post(
        f"/extractions/{job['id']}/proposals",
        json={"indexes": list(range(6))},
        headers=tenant.builder.headers,
    )
    assert proposed.status_code == 202, proposed.text
    proposals = proposed.json()
    assert {p["origin"] for p in proposals} == {"document"}
    detail = proposals[0]["originDetail"]
    assert (detail["fileName"], detail["mediaType"], detail["sentenceIndex"]) == (
        "plant.txt",
        "text/plain",
        0,
    )
    assert proposals[4]["originDetail"]["sentenceIndex"] == 3

    again = await client.post(
        f"/extractions/{job['id']}/proposals", json={"indexes": [0]}, headers=tenant.builder.headers
    )
    assert again.status_code == 409 and again.json()["code"] == "extraction_submitted"

    listed = await client.get("/proposals", headers=tenant.governor.headers)
    below = {p["title"]: p.get("openBelow", 0) for p in listed.json()["items"]}
    assert below["Paint shop"] == 3
    branch = await client.post(
        f"/proposals/{proposals[0]['id']}/approve-branch", headers=tenant.governor.headers
    )
    assert branch.status_code == 200, branch.text
    assert (branch.json()["approved"], branch.json()["complete"]) == (4, True)


async def test_a_job_without_a_model_fails_and_the_import_can_still_be_taught(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    import_id = await imported(client, tenant)
    job = (await start(client, tenant, import_id)).json()

    await document_extraction_runner_service.run_once()

    status = (await client.get(f"/extractions/{job['id']}", headers=tenant.builder.headers)).json()
    assert (status["state"], status["failureReason"]) == ("failed", "not_configured")
    result = await client.get(f"/extractions/{job['id']}/result", headers=tenant.builder.headers)
    assert result.status_code == 409 and result.json()["code"] == "extraction_not_ready"


async def test_an_invalid_chunk_is_unresolved_and_nothing_grounded_fails_the_job(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    import_id = await imported(client, tenant)
    job = (await start(client, tenant, import_id)).json()
    invalid = json.dumps(
        {"pass": "outline", "nodes": [node("k1", {"handle": "c0"}, "Paint shop", "is a", 0, "x")]}
    )
    fake_llm.answer(invalid, json.dumps({"pass": "section", "intents": [], "unresolved": []}))

    await document_extraction_runner_service.run_once()

    status = (await client.get(f"/extractions/{job['id']}", headers=tenant.builder.headers)).json()
    assert (status["state"], status["failureReason"]) == ("failed", "no_drafts")
    [stored] = await rows(
        "SELECT unresolved, drafts FROM ontaix.document_extraction_job WHERE id = :id",
        id=job["id"],
    )
    assert stored["drafts"] is None
    assert stored["unresolved"] == [{"chunk": 0, "reason": "model_invalid_output"}]
    calls = await rows(
        "SELECT purpose, outcome FROM ontaix.llm_call WHERE tenant_id = :t ORDER BY occurred_at",
        t=tenant.tenant_id,
    )
    assert [c["outcome"] for c in calls] == ["invalid_output", "used"]
    assert {c["purpose"] for c in calls} == {"document_extraction"}


async def test_start_rules_and_cancel(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    import_id = await imported(client, tenant)
    governor = await start(client, tenant, import_id, tenant.governor)
    assert governor.status_code == 404
    job = (await start(client, tenant, import_id)).json()
    again = await start(client, tenant, import_id)
    assert again.status_code == 409 and again.json()["code"] == "extraction_exists"
    second_import = await imported(client, tenant)
    running = await start(client, tenant, second_import)
    assert running.status_code == 409 and running.json()["code"] == "extraction_running"
    other = await client.get(f"/extractions/{job['id']}", headers=tenant.owner.headers)
    assert other.status_code == 404

    cancelled = await client.delete(f"/extractions/{job['id']}", headers=tenant.builder.headers)

    assert cancelled.status_code == 202, cancelled.text
    assert (cancelled.json()["state"], cancelled.json()["cancelRequested"]) == ("cancelled", True)
    assert (await start(client, tenant, second_import)).status_code == 202


async def test_a_lost_lease_writes_nothing_and_a_crashing_job_stops(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    import_id = await imported(client, tenant)
    job = (await start(client, tenant, import_id)).json()
    runner = uuid.uuid4()
    async with db_client.get_platform_session_factory()() as s:
        claimed = await document_extraction_job_repository.claimable(s)
        assert claimed is not None and str(claimed.id) == job["id"]
        epoch = await document_extraction_job_repository.take_lease(s, claimed, runner)
        await s.commit()
    async with db_client.get_platform_session_factory()() as s:
        stale = await document_extraction_job_repository.fenced_update(
            s, claimed.id, runner, epoch - 1, {"tokens_used": 99}
        )
        other = await document_extraction_job_repository.fenced_update(
            s, claimed.id, uuid.uuid4(), epoch, {"tokens_used": 99}
        )
        assert stale is None and other is None
        await s.execute(
            text(
                "UPDATE ontaix.document_extraction_job SET attempts = 3,"
                " lease_until = now() - interval '1 second' WHERE id = :id"
            ),
            {"id": job["id"]},
        )
        await s.commit()

    await document_extraction_runner_service.run_once()

    status = (await client.get(f"/extractions/{job['id']}", headers=tenant.builder.headers)).json()
    assert (status["state"], status["failureReason"], status["tokensUsed"]) == (
        "failed",
        "too_many_attempts",
        0,
    )
    assert fake_llm.requests == []


async def test_a_cancel_requested_while_running_ends_the_job(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    import_id = await imported(client, tenant)
    job = (await start(client, tenant, import_id)).json()
    fake = FakeLlmClient()
    set_llm_client(fake)
    async with db_client.get_platform_session_factory()() as s:
        await s.execute(
            text(
                "UPDATE ontaix.document_extraction_job SET state = 'running', phase = 'outline',"
                " cancel_requested = true WHERE id = :id"
            ),
            {"id": job["id"]},
        )
        await s.commit()

    await document_extraction_runner_service.run_once()

    status = (await client.get(f"/extractions/{job['id']}", headers=tenant.builder.headers)).json()
    assert status["state"] == "cancelled" and fake.requests == []


async def test_the_lease_is_renewed_while_mapping_runs(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    fake_llm: FakeLlmClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import_id = await imported(client, tenant)
    job = (await start(client, tenant, import_id)).json()
    fake_llm.answer(OUTLINE, SECTIONS)
    original = document_extraction_runner_service.map_tree
    renewals: list[object] = []

    def slow_map(*args: object) -> object:
        time.sleep(0.5)
        return original(*args)

    async def count_writes(self, values, *, event=False):  # type: ignore[no-untyped-def]
        if values == {}:
            renewals.append(values)
        await real_write(self, values, event=event)

    real_write = document_extraction_runner_service._Run._write
    monkeypatch.setattr(document_extraction_runner_service, "map_tree", slow_map)
    monkeypatch.setattr(document_extraction_runner_service, "RENEW_SECONDS", 0.05)
    monkeypatch.setattr(document_extraction_runner_service._Run, "_write", count_writes)

    await document_extraction_runner_service.run_once()

    status = (await client.get(f"/extractions/{job['id']}", headers=tenant.builder.headers)).json()
    assert status["state"] == "succeeded"
    assert len(renewals) >= 2
