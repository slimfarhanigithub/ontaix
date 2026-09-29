"""POST /concepts/{conceptId}/expand and POST /expansions/{expansionId}/proposals, against
recorded model answers."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from sqlalchemy import text

from app.clients import db_client
from app.clients.llm_client import LlmRefused, LlmTimeout, set_llm_client
from app.config import get_settings
from app.repositories import teach_session_turn_repository
from app.repositories.teach_session_turn_repository import SessionKey
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_proposals import approved, propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")


def suggestion(key: str, parent: str, label: str, action: str, confidence: float = 0.9) -> dict:
    return {
        "key": key,
        "parent": parent,
        "label": label,
        "action": action,
        "confidence": confidence,
        "rationale": f"{label} belongs here.",
    }


def link(a: str, b: str, action: str, confidence: float = 0.8) -> dict:
    return {"from": a, "to": b, "action": action, "confidence": confidence, "rationale": "Linked."}


SALES_ANSWER = json.dumps(
    {
        "suggestions": [
            suggestion("s1", "e0", "Orders", "handles"),
            suggestion("s2", "s1", "Order lines", "contains", 0.8),
            suggestion("s3", "e0", "Quotes", "issues", 0.3),
            suggestion("s4", "s3", "Quote terms", "has"),
            suggestion("s5", "e0", "Sale", "has"),
            suggestion("s6", "e0", "orders", "has"),
            suggestion("s7", "s2", "Line discounts", "has"),
        ],
        "links": [
            link("s2", "e0", "reports to", 0.7),
            link("s1", "s2", "contains"),
        ],
    }
)


async def rows(sql: str, **params: object) -> list[dict]:
    async with db_client.get_session_factory()() as s:
        result = await s.execute(text(sql), params)
        return [dict(r._mapping) for r in result]


async def expand(
    client: httpx.AsyncClient, tenant: TenantFixture, concept_id: str, body: dict | None = None
) -> httpx.Response:
    return await client.post(
        f"/concepts/{concept_id}/expand", json=body or {}, headers=tenant.builder.headers
    )


async def test_expansion_suggests_a_branch_of_any_depth_and_proposes_a_selection(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    sales = await approved(client, tenant, "Sales", "sales")
    fake_llm.answer(SALES_ANSWER)
    session_id = uuid.uuid4()

    response = await expand(
        client,
        tenant,
        sales["id"],
        {"depth": 2, "focus": "after-sales services", "sessionId": str(session_id)},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["llmOutcome"], body["degraded"]) == ("used", False)
    assert body["expansionId"] and body["expiresAt"]
    company = str(tenant.company_id)
    assert body["drafts"] == [
        {
            "type": "concept",
            "companyId": company,
            "parentId": sales["id"],
            "label": "Orders",
            "domainKey": "sales",
            "action": "handles",
            "reverse": False,
        },
        {
            "type": "concept",
            "companyId": company,
            "parentLabel": "Orders",
            "label": "Order lines",
            "domainKey": "sales",
            "action": "contains",
            "reverse": False,
        },
        {
            "type": "relation",
            "companyId": company,
            "action": "reports to",
            "aLabel": "Order lines",
            "bId": sales["id"],
        },
    ]
    assert [(n["depth"], n["requires"]) for n in body["notes"]] == [(1, []), (2, [0]), (None, [1])]
    assert body["notes"][0] == {
        "confidence": 0.9,
        "rationale": "Orders belongs here.",
        "depth": 1,
        "requires": [],
    }
    assert {(s["label"], s["reason"]) for s in body["skipped"]} == {
        ("Quotes", "low_confidence"),
        ("Quote terms", "parent_skipped"),
        ("Sale", "existing_label"),
        ("Orders", "duplicate_in_response"),
        ("Line discounts", "over_cap"),
        ("Orders contains Order lines", "duplicate_relation"),
    }

    sent = fake_llm.context()
    assert sent["expanded"] == {
        "handle": "e0",
        "label": "Sales",
        "domain": "sales",
        "isRoot": False,
    }
    assert sent["ancestors"] == [tenant.company_name]
    assert (sent["focus"], sent["depth"], sent["maxChildren"]) == ("after-sales services", 2, None)
    user = fake_llm.requests[0].user
    for secret in (sales["id"], str(tenant.tenant_id), str(tenant.company_id), str(session_id)):
        assert secret not in user
    allowance = get_settings().llm_profile("deep").reasoning_allowance_tokens
    assert fake_llm.requests[0].max_output_tokens == 128 * 200 + allowance
    assert fake_llm.requests[0].timeout_seconds == 120

    [call] = await rows(
        "SELECT purpose, outcome, company_id FROM ontaix.llm_call WHERE tenant_id = :t",
        t=tenant.tenant_id,
    )
    assert call == {
        "purpose": "concept_expansion",
        "outcome": "used",
        "company_id": tenant.company_id,
    }
    assert (
        await rows(
            "SELECT 1 FROM ontaix.proposal WHERE tenant_id = :t AND title = 'Orders'",
            t=tenant.tenant_id,
        )
        == []
    )

    refused = await client.post(
        f"/expansions/{body['expansionId']}/proposals",
        json={"indexes": [1]},
        headers=tenant.builder.headers,
    )
    assert refused.status_code == 422, refused.text

    created = await client.post(
        f"/expansions/{body['expansionId']}/proposals",
        json={"indexes": [2, 0, 1]},
        headers=tenant.builder.headers,
    )
    assert created.status_code == 202, created.text
    proposals = created.json()
    assert [p["title"] for p in proposals] == [
        "Orders",
        "Order lines",
        "Order lines reports to Sales",
    ]
    assert {p["origin"] for p in proposals} == {"suggestion"}
    assert all(p["originDetail"] is None for p in proposals)
    assert proposals[0]["heading"] == "New concept · Sales · suggested"
    assert proposals[2]["heading"] == "Relation · suggested"
    assert proposals[0]["why"] == "Suggested by the model · 90% · Orders belongs here."
    assert proposals[1]["why"] == "Suggested by the model · 80% · Order lines belongs here."

    again = await client.post(
        f"/expansions/{body['expansionId']}/proposals",
        json={"indexes": [0]},
        headers=tenant.builder.headers,
    )
    assert again.status_code == 409 and again.json()["code"] == "expansion_submitted"

    async with db_client.get_session_factory()() as s:
        turns = await teach_session_turn_repository.recent(
            s,
            SessionKey(
                tenant.tenant_id, "user", tenant.builder.user_id, tenant.company_id, session_id
            ),
        )
    assert [(t.sentence, t.new_labels) for t in turns] == [
        ("Expand Sales", ["Orders", "Order lines"])
    ]


async def test_the_company_root_expands_into_domains_and_nothing_is_stored_without_drafts(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    root_answer = {
        "suggestions": [
            {**suggestion("s1", "e0", "Logistics hub", "runs"), "domainKey": "logistics"},
            suggestion("s2", "e0", "Workshop", "runs"),
        ],
        "links": [],
    }
    fake_llm.answer(json.dumps(root_answer), json.dumps({"suggestions": [], "links": []}))

    first = await expand(client, tenant, str(tenant.root_id), {"maxChildren": 1})

    assert first.status_code == 200, first.text
    body = first.json()
    assert [(d["label"], d["domainKey"], d["parentId"]) for d in body["drafts"]] == [
        ("Logistics hub", "logistics", str(tenant.root_id))
    ]
    assert body["skipped"] == [{"label": "Workshop", "reason": "over_cap"}]
    assert fake_llm.context()["expanded"]["isRoot"] is True

    empty = await expand(client, tenant, str(tenant.root_id))
    assert empty.status_code == 200
    assert (empty.json()["expansionId"], empty.json()["drafts"]) == (None, [])


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (LlmTimeout("timeout"), "timeout"),
        (LlmRefused("refusal", 10, 0, 0.0, 5), "refused"),
        (
            json.dumps({"suggestions": [suggestion("s1", "e0", "Kinds", "is a")], "links": []}),
            "invalid_output",
        ),
        (
            json.dumps({"suggestions": [suggestion("s1", "s9", "Orphans", "has")], "links": []}),
            "invalid_output",
        ),
        (
            json.dumps({"suggestions": [suggestion("s1", "e0", "Hidden​text", "has")], "links": []}),
            "invalid_output",
        ),
    ],
)
async def test_a_failed_or_refused_answer_is_a_degraded_200(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    fake_llm: FakeLlmClient,
    answer: object,
    outcome: str,
) -> None:
    fake_llm.answer(answer)  # type: ignore[arg-type]

    response = await expand(client, tenant, str(tenant.root_id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["llmOutcome"], body["degraded"], body["drafts"]) == (outcome, True, [])
    [call] = await rows(
        "SELECT outcome FROM ontaix.llm_call WHERE tenant_id = :t", t=tenant.tenant_id
    )
    assert call["outcome"] == outcome


async def test_without_a_model_or_budget_expansion_answers_without_calling(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await expand(client, tenant, str(tenant.root_id))
    assert response.json()["llmOutcome"] == "not_configured"

    async with db_client.get_session_factory()() as s:
        await s.execute(
            text(
                "UPDATE ontaix.tenant_settings SET llm_monthly_token_cap = 0 WHERE tenant_id = :t"
            ),
            {"t": tenant.tenant_id},
        )
        await s.commit()
    set_llm_client(FakeLlmClient())
    capped = await expand(client, tenant, str(tenant.root_id))
    assert capped.json()["llmOutcome"] == "budget_exhausted"


async def test_expansion_is_for_owners_and_builders_on_approved_concepts(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    pending = await propose_concept(client, tenant, tenant.builder, "Pending thing", tenant.root_id)
    pending_id = pending.json()["conceptId"]

    governor = await client.post(
        f"/concepts/{tenant.root_id}/expand", json={}, headers=tenant.governor.headers
    )
    assert governor.status_code == 403
    outsider = await client.post(
        f"/concepts/{tenant.root_id}/expand", json={}, headers=tenant.outsider.headers
    )
    assert outsider.status_code == 404
    waiting = await expand(client, tenant, pending_id)
    assert waiting.status_code == 409 and waiting.json()["code"] == "concept_pending"
    unknown = await expand(client, tenant, str(uuid.uuid4()))
    assert unknown.status_code == 404
    markup = await expand(client, tenant, str(tenant.root_id), {"focus": "<b>x</b>"})
    assert markup.status_code == 422
    assert fake_llm.requests == []


async def test_the_expand_budget_is_charged_first(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    fake_llm: FakeLlmClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ONTAIX_EXPAND_CALLS_PER_HOUR", "1")
    get_settings.cache_clear()
    try:
        fake_llm.answer(json.dumps({"suggestions": [], "links": []}))
        assert (await expand(client, tenant, str(tenant.root_id))).status_code == 200
        second = await expand(client, tenant, str(tenant.root_id))
    finally:
        monkeypatch.delenv("ONTAIX_EXPAND_CALLS_PER_HOUR")
        get_settings.cache_clear()
    assert second.status_code == 429 and second.headers["Retry-After"]
    assert len(fake_llm.requests) == 1


async def test_an_expansion_belongs_to_its_user_and_expires(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    fake_llm.answer(
        json.dumps({"suggestions": [suggestion("s1", "e0", "Studio", "runs")], "links": []})
    )
    body = (await expand(client, tenant, str(tenant.root_id))).json()
    expansion = body["expansionId"]

    other = await client.post(
        f"/expansions/{expansion}/proposals", json={"indexes": [0]}, headers=tenant.owner.headers
    )
    assert other.status_code == 404

    async with db_client.get_session_factory()() as s:
        await s.execute(
            text(
                "UPDATE ontaix.concept_expansion SET created_at = now() - interval '2 hours',"
                " expires_at = now() - interval '1 hour' WHERE id = :id"
            ),
            {"id": expansion},
        )
        await s.commit()
    expired = await client.post(
        f"/expansions/{expansion}/proposals", json={"indexes": [0]}, headers=tenant.builder.headers
    )
    assert expired.status_code == 410 and expired.json()["code"] == "expansion_expired"
