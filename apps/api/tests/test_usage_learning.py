"""Usage learning: parse records and proposal links, lessons from decisions, corrections and
speech aliases, what a model call receives, per-company and per-tenant isolation, the
administration endpoints, contradiction, the switches and the purge. No test reaches a model."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import pytest
from sqlalchemy import select, text

from app.clients import db_client
from app.config import get_settings
from app.models.storage.audit_entry import AuditEntry
from app.models.storage.base import RoleName, ScopeKind
from app.repositories import (
    app_user_repository,
    group_member_repository,
    group_role_repository,
    learning_example_repository,
    tenant_repository,
    tenant_settings_repository,
    user_group_repository,
    view_state_repository,
)
from app.services import company_service, learning_service
from app.services.ontology_view_service import load_view
from app.services.teach_extraction_service import alias_grounding
from tests.conftest import DEV_ISSUER, Persona, TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_teach_extraction import configure

pytestmark = pytest.mark.asyncio(loop_scope="session")

SENTENCE = "In sales, a customer places orders."
RE_TEACH = "A customer places purchase orders"
SPOKEN = "A plant has custommers"
RE_SPOKEN = "A plant has customers"


@dataclass(frozen=True)
class OtherTenant:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    admin: Persona


async def parse(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    persona: Persona,
    sentence: str,
    origin: str | None = None,
    session_id: uuid.UUID | None = None,
) -> dict:
    body: dict = {"companyId": str(tenant.company_id), "text": sentence}
    if origin:
        body["origin"] = origin
    if session_id:
        body["sessionId"] = str(session_id)
    response = await client.post("/teach/parse", json=body, headers=persona.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def batch(
    client: httpx.AsyncClient,
    persona: Persona,
    result: dict,
    drafts: list[dict] | None = None,
    parse_id: str | None | bool = True,
) -> list[dict]:
    body: dict = {"drafts": drafts if drafts is not None else result["drafts"]}
    if parse_id is True:
        body["parseId"] = result["parseId"]
    elif parse_id:
        body["parseId"] = parse_id
    response = await client.post("/proposals/batch", json=body, headers=persona.headers)
    assert response.status_code == 202, response.text
    return response.json()


async def decide(
    client: httpx.AsyncClient, persona: Persona, proposal_id: str, verb: str = "approve"
) -> dict:
    response = await client.post(f"/proposals/{proposal_id}/{verb}", headers=persona.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def rows(sql: str, **params: object) -> list[dict]:
    async with db_client.get_session_factory()() as s:
        result = await s.execute(text(sql), params)
        return [dict(r._mapping) for r in result]


async def lessons_of(tenant: TenantFixture, company_id: uuid.UUID | None = None) -> list[dict]:
    return await rows(
        "SELECT * FROM ontaix.learning_example WHERE tenant_id = :t AND company_id = :c"
        " ORDER BY created_at, id",
        t=tenant.tenant_id,
        c=company_id or tenant.company_id,
    )


async def aliases_of(tenant: TenantFixture) -> list[dict]:
    return await rows(
        "SELECT * FROM ontaix.company_alias WHERE tenant_id = :t AND company_id = :c"
        " ORDER BY created_at",
        t=tenant.tenant_id,
        c=tenant.company_id,
    )


async def learning_audit(tenant: TenantFixture) -> list[AuditEntry]:
    async with db_client.get_session_factory()() as s:
        found = await s.scalars(
            select(AuditEntry)
            .where(AuditEntry.tenant_id == tenant.tenant_id, AuditEntry.kind == "learning")
            .order_by(AuditEntry.id)
        )
        return list(found)


async def other_tenant() -> OtherTenant:
    """A second tenant with one company and one Administrator."""
    slug = f"o-{uuid.uuid4().hex[:10]}"
    async with db_client.get_session_factory()() as s:
        t = await tenant_repository.create(s, slug, f"Tenant {slug}")
        await tenant_settings_repository.create(s, t.id)
        await view_state_repository.create(s, t.id)
        subject = f"admin@{slug}.test"
        user = await app_user_repository.create(
            s,
            tenant_id=t.id,
            issuer=DEV_ISSUER,
            subject=subject,
            email=subject,
            name="Admin",
            department=None,
            company_id=None,
        )
        view = await load_view(s, t.id)
        company = await company_service.add_company(s, view, f"Other {slug}", "", is_home=True)
        group = await user_group_repository.create(s, t.id, "admins", "")
        await group_member_repository.add(s, t.id, group.id, user.id)
        await group_role_repository.create(
            s,
            tenant_id=t.id,
            group_id=group.id,
            role=RoleName.ADMINISTRATOR,
            scope_kind=ScopeKind.TENANT,
            scope_company_id=None,
            scope_domain_key=None,
        )
        await s.commit()
        return OtherTenant(t.id, company.id, Persona(subject=subject, user_id=user.id))


async def taught_and_approved(
    client: httpx.AsyncClient, tenant: TenantFixture, sentence: str = SENTENCE
) -> list[dict]:
    """The owner teaches `sentence` and approves the first draft; returns the proposals."""
    result = await parse(client, tenant, tenant.owner, sentence)
    created = await batch(client, tenant.owner, result)
    await decide(client, tenant.owner, created[0]["id"])
    return created


async def test_a_users_parse_is_recorded_and_the_batch_links_each_draft(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    result = await parse(client, tenant, tenant.owner, SENTENCE)

    assert result["parseId"]
    [stored] = await rows(
        "SELECT source_text, origin, extractor, company_id, actor_user_id, session_id,"
        " model_output FROM ontaix.teach_parse WHERE id = :id",
        id=result["parseId"],
    )
    assert stored["source_text"] == SENTENCE
    assert (stored["origin"], stored["extractor"]) == ("text", "rules")
    assert stored["company_id"] == tenant.company_id
    assert stored["actor_user_id"] == tenant.owner.user_id
    assert stored["model_output"]["drafts"] == result["drafts"]
    assert [i["kind"] for i in stored["model_output"]["intents"]] == ["rel"]

    edited = [result["drafts"][0], {**result["drafts"][1], "label": "Purchase order"}]
    created = await batch(client, tenant.owner, result, drafts=edited)
    links = await rows(
        "SELECT proposal_id, kind, draft_index, edited FROM ontaix.proposal_learning_source"
        " WHERE parse_id = :id ORDER BY draft_index",
        id=result["parseId"],
    )
    assert [(str(link["proposal_id"]), link["kind"]) for link in links] == [
        (created[0]["id"], "teach"),
        (created[1]["id"], "teach"),
    ]
    assert [(link["draft_index"], link["edited"]) for link in links] == [(0, False), (1, True)]


async def test_a_foreign_or_unknown_parse_id_is_ignored_silently(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    result = await parse(client, tenant, tenant.owner, "A plant has machines")

    by_another_user = await batch(client, tenant.builder, result)
    unknown = await batch(
        client,
        tenant.owner,
        result,
        drafts=[{**result["drafts"][0], "label": "Line"}],
        parse_id=str(uuid.uuid4()),
    )

    assert len(by_another_user) == 2 and len(unknown) == 1
    assert (
        await rows(
            "SELECT count(*) AS n FROM ontaix.proposal_learning_source WHERE tenant_id = :t",
            t=tenant.tenant_id,
        )
    )[0]["n"] == 0


async def test_approve_reject_and_a_re_teach_become_lessons_and_a_correction(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    customer, order = await taught_and_approved(client, tenant)

    [approve] = await lessons_of(tenant)
    assert (approve["signal"], approve["task"], approve["origin"]) == ("approve", "teach", "text")
    assert approve["source_text"] == SENTENCE and approve["bulk"] is False
    assert approve["model_output"] is None
    assert approve["final_structure"] == {
        "drafts": [
            {
                "type": "concept",
                "label": "Customer",
                "parent": tenant.company_name,
                "action": "has",
                "domain": "sales",
            }
        ]
    }
    assert [str(i) for i in approve["proposal_ids"]] == [customer["id"]]
    assert [str(i) for i in approve["concept_ids"]] == [customer["conceptId"]]
    assert approve["actor_user_id"] == tenant.owner.user_id

    await decide(client, tenant.owner, order["id"], "reject")
    _, reject = await lessons_of(tenant)
    assert (reject["signal"], reject["bulk"], reject["final_structure"]) == ("reject", False, None)
    assert reject["model_output"] == {
        "drafts": [
            {
                "type": "concept",
                "label": "Order",
                "parent": "Customer",
                "action": "places",
                "domain": "sales",
            }
        ]
    }

    again = await parse(client, tenant, tenant.owner, RE_TEACH)
    [purchase_order] = await batch(client, tenant.owner, again)
    await decide(client, tenant.governor, purchase_order["id"])

    kept, negative, correct = await lessons_of(tenant)
    assert kept["retired_at"] is None
    assert negative["id"] == reject["id"] and negative["retired_at"] is None
    assert (correct["signal"], correct["origin"], correct["bulk"]) == ("correct", "text", False)
    assert correct["corrects_id"] == reject["id"]
    assert correct["source_text"] == RE_TEACH
    assert correct["model_output"] == reject["model_output"]
    assert correct["final_structure"] == {
        "drafts": [
            {
                "type": "concept",
                "label": "Purchase order",
                "parent": "Customer",
                "action": "places",
                "domain": "sales",
            }
        ]
    }
    assert correct["actor_user_id"] == tenant.governor.user_id


async def test_bulk_approvals_are_kept_as_bulk(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    result = await parse(client, tenant, tenant.owner, "A plant has machines")
    await batch(client, tenant.owner, result)

    response = await client.post("/proposals/approve-all", headers=tenant.governor.headers)

    assert response.status_code == 200, response.text
    [lesson] = await lessons_of(tenant)
    assert lesson["bulk"] is True
    assert [d["label"] for d in lesson["final_structure"]["drafts"]] == ["Plant", "Machine"]


async def test_a_speech_correction_learns_an_alias_and_the_model_receives_the_learning(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    # The grammar seeds the lessons with the step off: a step that is on but does not answer
    # drafts nothing for speech.
    await configure(tenant, llm_monthly_token_cap=0)
    spoken = await parse(client, tenant, tenant.owner, SPOKEN, origin="speech")
    plant, custommer = await batch(client, tenant.owner, spoken)
    await decide(client, tenant.owner, plant["id"])
    await decide(client, tenant.owner, custommer["id"], "reject")
    again = await parse(client, tenant, tenant.owner, RE_SPOKEN, origin="speech")
    [customer] = await batch(client, tenant.owner, again)
    await decide(client, tenant.owner, customer["id"])

    [alias] = await aliases_of(tenant)
    assert (alias["heard"], alias["meant"]) == ("Custommer", "Customer")
    assert str(alias["concept_id"]) == customer["conceptId"]
    assert alias["retired_at"] is None and alias["hits"] == 0
    signals = [(lesson["signal"], lesson["origin"]) for lesson in await lessons_of(tenant)]
    assert signals == [("approve", "speech"), ("reject", "speech"), ("correct", "speech")]

    await configure(tenant)
    sentence = "In the plant the custommer signs contracts"
    fake_llm.answer(_answer_citing("Customer", "Contract", "signs", sentence))
    result = await parse(client, tenant, tenant.owner, sentence)

    assert result["llmOutcome"] == "used", result
    data = fake_llm.context(-1)
    keys = list(data)
    assert keys[0] == "examples"
    assert keys.index("domainTemplates") < keys.index("companyLessons")
    assert data["companyAliases"] == [{"heard": "Custommer", "meant": "Customer"}]
    assert [lesson["input"] for lesson in data["companyLessons"]][0] == RE_SPOKEN
    assert data["companyLessons"][0]["personMeant"][0]["label"] == "Customer"
    assert data["companyLessons"][0]["modelProduced"][0]["label"] == "Custommer"
    assert {lesson["input"] for lesson in data["companyLessons"]} == {SPOKEN, RE_SPOKEN}
    assert data["companyNegatives"] == [
        {
            "input": SPOKEN,
            "rejected": [
                {
                    "type": "concept",
                    "label": "Custommer",
                    "parent": "Plant",
                    "action": "has",
                    "domain": "production",
                }
            ],
        }
    ]
    assert data["companyHabits"].startswith("Preferred actions: has")
    [alias] = await aliases_of(tenant)
    assert alias["hits"] == 1
    assert fake_llm.requests[-1].system.count("companyAliases") == 1


async def test_an_alias_grounds_its_meant_label_where_the_heard_form_is_said() -> None:
    aliases = [("Custommer", "Customer")]
    sentence = "the custommer signs contracts"

    assert alias_grounding("Customer", sentence, (0, len(sentence)), aliases) == "Customer"
    assert alias_grounding("customer", sentence, (0, len(sentence)), aliases) == "Customer"
    assert alias_grounding("Customer", "the client signs contracts", (0, 26), aliases) is None
    assert alias_grounding("Contract", sentence, (0, len(sentence)), aliases) is None
    assert alias_grounding("Customer", sentence, (14, len(sentence)), aliases) is None


async def test_an_approved_rename_of_a_concept_born_from_speech_learns_an_alias(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    spoken = await parse(client, tenant, tenant.owner, SPOKEN, origin="speech")
    plant, custommer = await batch(client, tenant.owner, spoken)
    await decide(client, tenant.owner, plant["id"])
    await decide(client, tenant.owner, custommer["id"])
    rename = await client.patch(
        f"/concepts/{custommer['conceptId']}",
        json={"label": "Customer"},
        headers=tenant.owner.headers,
    )
    assert rename.status_code == 202, rename.text

    await decide(client, tenant.owner, rename.json()["id"])

    [alias] = await aliases_of(tenant)
    assert (alias["heard"], alias["meant"]) == ("Custommer", "Customer")
    assert str(alias["concept_id"]) == custommer["conceptId"]


async def test_lessons_never_cross_a_company_or_a_tenant(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    await taught_and_approved(client, tenant)
    other_company = await client.post(
        "/companies", json={"name": "Elsewhere", "start": "one_cell"}, headers=tenant.admin.headers
    )
    assert other_company.status_code == 201, other_company.text
    elsewhere = uuid.UUID(other_company.json()["company"]["id"])
    other = await other_tenant()

    async with db_client.get_session_factory()() as s:
        home_view = await load_view(s, tenant.tenant_id)
        other_view = await load_view(s, other.tenant_id)
        assert (
            await learning_example_repository.list_active(s, other.tenant_id, other.company_id)
            == []
        )
        assert await learning_example_repository.list_active(s, tenant.tenant_id, elsewhere) == []
    home = await learning_service.context_for(home_view, tenant.company_id, SENTENCE, "teach")
    sibling = await learning_service.context_for(home_view, elsewhere, SENTENCE, "teach")
    foreign = await learning_service.context_for(other_view, other.company_id, SENTENCE, "teach")

    assert home is not None and [lesson["input"] for lesson in home.lessons] == [SENTENCE]
    assert sibling is not None and sibling.lessons == [] and sibling.negatives == []
    assert foreign is not None and foreign.lessons == [] and foreign.negatives == []
    listed = await client.get(
        f"/companies/{tenant.company_id}/learning", headers=other.admin.headers
    )
    assert listed.status_code == 404
    mine = await client.get(f"/companies/{elsewhere}/learning", headers=tenant.admin.headers)
    assert mine.status_code == 200 and mine.json()["total"] == 0
    assert (
        await client.get(f"/companies/{tenant.company_id}/learning", headers=tenant.admin.headers)
    ).json()["total"] == 1


async def test_administrators_list_switch_delete_and_reset_learning(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    await taught_and_approved(client, tenant)
    url = f"/companies/{tenant.company_id}/learning"

    assert (await client.get(url, headers=tenant.builder.headers)).status_code == 403
    assert (await client.get(url, headers=tenant.governor.headers)).status_code == 403
    listed = await client.get(url, headers=tenant.admin.headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["companyId"] == str(tenant.company_id) and body["enabled"] is True
    assert (body["page"], body["pageSize"], body["total"]) == (1, 40, 1)
    [lesson] = body["lessons"]
    assert lesson["signal"] == "approve" and lesson["sourceText"] == SENTENCE
    assert lesson["retiredAt"] is None and lesson["retiredReason"] is None
    assert body["aliases"] == []
    assert body["habits"]["verbs"][0]["action"] == "has"
    filtered = await client.get(f"{url}?filter[signal]=reject", headers=tenant.admin.headers)
    assert filtered.json()["total"] == 0
    assert (
        await client.get(f"{url}?filter[state]=x", headers=tenant.admin.headers)
    ).status_code == 400

    off = await client.patch(url, json={"enabled": False}, headers=tenant.admin.headers)
    assert off.status_code == 200 and off.json() == {
        "companyId": str(tenant.company_id),
        "enabled": False,
    }
    silent = await parse(client, tenant, tenant.owner, "A plant has machines")
    assert silent["parseId"] is None
    assert (await client.get(url, headers=tenant.admin.headers)).json()["enabled"] is False
    on = await client.patch(url, json={"enabled": True}, headers=tenant.admin.headers)
    assert on.json()["enabled"] is True

    deleted = await client.delete(f"{url}/{lesson['id']}", headers=tenant.admin.headers)
    assert deleted.status_code == 204
    assert (
        await client.delete(f"{url}/{lesson['id']}", headers=tenant.admin.headers)
    ).status_code == 404
    assert (await client.get(url, headers=tenant.admin.headers)).json()["total"] == 0

    await taught_and_approved(client, tenant, "In sales, a supplier ships parcels.")
    missing = await client.post(f"{url}/reset", json={}, headers=tenant.admin.headers)
    wrong = await client.post(
        f"{url}/reset", json={"confirm": "nope"}, headers=tenant.admin.headers
    )
    assert (missing.status_code, missing.json()["code"]) == (422, "confirmation_required")
    assert (wrong.status_code, wrong.json()["code"]) == (422, "confirmation_mismatch")
    reset = await client.post(
        f"{url}/reset", json={"confirm": "reset"}, headers=tenant.admin.headers
    )
    assert reset.status_code == 200 and reset.json() == {"lessons": 1, "aliases": 0}
    assert (await client.get(url, headers=tenant.admin.headers)).json()["total"] == 0
    assert (
        await rows(
            "SELECT count(*) AS n FROM ontaix.teach_parse WHERE company_id = :c",
            c=tenant.company_id,
        )
    )[0]["n"] == 0

    entries = [(e.what, e.ok, list(e.company_ids)) for e in await learning_audit(tenant)]
    assert entries == [
        (f"Learning disabled for {tenant.company_name}", True, [tenant.company_id]),
        (f"Learning enabled for {tenant.company_name}", True, [tenant.company_id]),
        ("Lesson deleted", True, [tenant.company_id]),
        (
            f"Learning reset for {tenant.company_name} - 1 lessons, 0 aliases",
            True,
            [tenant.company_id],
        ),
    ]
    assert all(SENTENCE not in e.what for e in await learning_audit(tenant))


async def test_deleting_an_approved_concept_retires_its_lesson_and_teaches_a_negative(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    customer, _ = await taught_and_approved(client, tenant)
    removal = await client.delete(
        f"/concepts/{customer['conceptId']}", headers=tenant.owner.headers
    )
    assert removal.status_code == 202, removal.text

    await decide(client, tenant.owner, removal.json()["id"])

    retired, negative = await lessons_of(tenant)
    assert (retired["signal"], retired["retired_reason"]) == ("approve", "contradicted")
    assert retired["retired_at"] is not None
    assert (negative["signal"], negative["retired_at"]) == ("reject", None)
    assert negative["model_output"] == retired["final_structure"]
    assert negative["source_text"] == SENTENCE


async def test_the_deployment_switch_stops_capture(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "learning_enabled", False)

    result = await parse(client, tenant, tenant.owner, SENTENCE)

    assert result["parseId"] is None
    assert await lessons_of(tenant) == []


async def test_the_purge_removes_expired_parses_and_old_retired_rows(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    customer, _ = await taught_and_approved(client, tenant)
    result = await parse(client, tenant, tenant.owner, "A plant has machines")
    async with db_client.get_session_factory()() as s:
        await s.execute(
            text(
                "UPDATE ontaix.teach_parse SET created_at = now() - interval '8 days',"
                " expires_at = now() - interval '1 day' WHERE id = :id"
            ),
            {"id": result["parseId"]},
        )
        await s.execute(
            text(
                "UPDATE ontaix.learning_example SET retired_at = now() - interval '31 days',"
                " retired_reason = 'cap' WHERE company_id = :c"
            ),
            {"c": tenant.company_id},
        )
        await s.commit()

    parses, retired = await learning_service.purge_expired()

    assert parses >= 1 and retired >= 1
    assert await lessons_of(tenant) == []
    assert (
        await rows(
            "SELECT count(*) AS n FROM ontaix.teach_parse WHERE id = :id", id=result["parseId"]
        )
    )[0]["n"] == 0


def _answer_citing(
    subject: str, new_label: str, action: str, sentence: str
) -> Callable[[dict], str]:
    """A model answer relating the candidate labelled `subject` to `new_label`."""

    def build(data: dict) -> str:
        handle = next(c["handle"] for c in data["candidates"] if c["label"] == subject)
        start = sentence.index("custommer")
        return json.dumps(
            {
                "intents": [
                    {
                        "kind": "rel",
                        "subject": {"candidate": handle},
                        "object": {"newLabel": new_label},
                        "action": action,
                        "confidence": 0.9,
                        "span": sentence[start:],
                        "source": {"start": start, "end": len(sentence)},
                    }
                ],
                "unresolved": [],
            }
        )

    return build
