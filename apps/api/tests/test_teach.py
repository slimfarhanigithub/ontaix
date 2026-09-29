"""POST /teach/parse: the grammar, typed text and speech transcripts, and the channel gates."""

from __future__ import annotations

import httpx
import pytest

from app.clients import db_client
from app.repositories import tenant_settings_repository
from tests.conftest import TenantFixture

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def set_settings(tenant: TenantFixture, **values: bool) -> None:
    async with db_client.get_session_factory()() as s:
        settings = await tenant_settings_repository.get(s, tenant.tenant_id)
        assert settings is not None
        for name, value in values.items():
            setattr(settings, name, value)
        await s.commit()


async def parse(
    client: httpx.AsyncClient, tenant: TenantFixture, text: str, origin: str | None = None
) -> httpx.Response:
    body: dict = {"companyId": str(tenant.company_id), "text": text}
    if origin:
        body["origin"] = origin
    return await client.post("/teach/parse", json=body, headers=tenant.builder.headers)


async def test_typed_text_is_understood_and_its_drafts_become_text_proposals(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await parse(client, tenant, "In sales, a customer places orders.")

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "understood"
    assert result["domainKey"] == "sales"
    assert result["origin"] == "text" and result["originDetail"] is None
    assert result["statements"] == ["Customer places Order (both new)"]
    first, second = result["drafts"]
    assert first == {
        "origin": "text",
        "type": "concept",
        "companyId": str(tenant.company_id),
        "parentId": str(tenant.root_id),
        "label": "Customer",
        "domainKey": "sales",
        "action": "has",
    }
    assert second["parentLabel"] == "Customer" and "parentId" not in second
    assert result["caption"].endswith("Waiting for your approval on the right.")

    created = await client.post(
        "/proposals/batch", json={"drafts": result["drafts"]}, headers=tenant.builder.headers
    )
    assert created.status_code == 202, created.text
    assert [(p["origin"], p["originDetail"]) for p in created.json()] == [("text", None)] * 2

    approved = await client.post(
        f"/proposals/{created.json()[0]['id']}/approve", headers=tenant.governor.headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["audit"]["origin"] == "text"


async def test_a_sentence_naming_known_concepts_links_them(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    result = (await parse(client, tenant, "A plant has machines")).json()
    await client.post(
        "/proposals/batch", json={"drafts": result["drafts"]}, headers=tenant.builder.headers
    )

    again = (await parse(client, tenant, "Machines feed the plant")).json()

    assert again["outcome"] == "understood"
    [draft] = again["drafts"]
    assert draft["type"] == "relation" and draft["action"] == "feeds"
    assert again["intents"][0]["subjectResolved"] == draft["aId"]


async def test_partly_and_not_understood(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    result = (await parse(client, tenant, "A plant has machines")).json()
    await client.post(
        "/proposals/batch", json={"drafts": result["drafts"]}, headers=tenant.builder.headers
    )

    partly = (await parse(client, tenant, "Plant downtime reports")).json()
    nothing = (await parse(client, tenant, "Hello there")).json()

    assert partly["outcome"] == "partly_understood"
    assert [d["label"] for d in partly["drafts"]] == ["Downtime", "Report"]
    assert all(d["action"] == "relates to" for d in partly["drafts"])
    assert partly["caption"].startswith("No action found; Downtime, Report proposed from Plant")
    assert nothing["outcome"] == "not_understood" and nothing["drafts"] == []


async def test_speech_transcripts_record_speech_and_are_gated_by_voice(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    result = (await parse(client, tenant, "A plant has machines", origin="speech")).json()
    assert result["origin"] == "speech"
    assert all(d["origin"] == "speech" for d in result["drafts"])
    created = await client.post(
        "/proposals/batch", json={"drafts": result["drafts"]}, headers=tenant.builder.headers
    )
    assert created.status_code == 202, created.text
    assert {p["origin"] for p in created.json()} == {"speech"}

    await set_settings(tenant, voice=False)
    refused_parse = await parse(client, tenant, "A line has shifts", origin="speech")
    refused_batch = await client.post(
        "/proposals/batch",
        json={"origin": "speech", "drafts": [{**result["drafts"][0], "label": "Line"}]},
        headers=tenant.builder.headers,
    )
    typed = await parse(client, tenant, "A line has shifts")

    assert refused_parse.status_code == 409
    assert refused_parse.json()["code"] == "channel_disabled"
    assert refused_batch.status_code == 409
    assert refused_batch.json()["code"] == "channel_disabled"
    assert typed.status_code == 200


async def test_live_teaching_off_refuses_typed_text(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    await set_settings(tenant, live_teaching=False)

    response = await parse(client, tenant, "A plant has machines")

    assert response.status_code == 409
    assert response.json()["code"] == "channel_disabled"


async def test_text_and_import_ref_are_mutually_exclusive(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    neither = await client.post(
        "/teach/parse", json={"companyId": str(tenant.company_id)}, headers=tenant.builder.headers
    )
    both = await client.post(
        "/teach/parse",
        json={
            "companyId": str(tenant.company_id),
            "text": "A plant has machines",
            "importRef": {"importId": str(tenant.tenant_id), "sentenceIndex": 0},
        },
        headers=tenant.builder.headers,
    )

    assert neither.status_code == 422
    assert both.status_code == 422


async def test_outsider_cannot_parse(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    response = await client.post(
        "/teach/parse",
        json={"companyId": str(tenant.company_id), "text": "A plant has machines"},
        headers=tenant.outsider.headers,
    )

    assert response.status_code in (403, 404)
