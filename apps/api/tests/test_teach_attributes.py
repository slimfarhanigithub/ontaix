"""Attribute intents: a spoken fact about a concept becomes a taught attribute proposal.

The regression case is the owner's recording, where `the managed ones are billed monthly` and
`advisory is billed per day` follow the sentences that introduced Advisory and Managed services.
Recorded answers only; no test reaches a provider.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import jsonschema
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.ai.prompts.teach_extraction import OUTPUT_SCHEMA
from app.clients import db_client
from app.models.llm.teach_extraction_answer import TeachExtractionAnswer
from app.services.teach_extraction_service import _ground_name, _ground_value
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_teach_extraction import add_company, configure, rows
from tests.test_teach_speech import speak, submit

CONTRACT = json.loads(
    (Path(__file__).parents[3] / "contracts" / "teach-extraction.schema.json").read_text(
        encoding="utf-8"
    )
)
MONTHLY = "the managed ones are billed monthly"
PER_DAY = "advisory is billed per day"


def attr(sentence: str, subject: dict, name: str, value: str, **extra: object) -> dict:
    return {
        "kind": "attr",
        "subject": subject,
        "attributeName": name,
        "attributeValue": value,
        "confidence": 0.9,
        "span": sentence,
        "segment": 0,
        "source": {"start": 0, "end": len(sentence)},
        **extra,
    }


def spoken(sentence: str, intents: list[dict]) -> str:
    return json.dumps(
        {
            "intents": intents,
            "unresolved": [],
            "segments": [{"index": 0, "start": 0, "end": len(sentence)}],
        }
    )


def handle(context: dict, label: str) -> str:
    return next(c["handle"] for c in context["candidates"] if c["label"] == label)


async def approve(client: httpx.AsyncClient, tenant: TenantFixture, proposal_id: str) -> dict:
    response = await client.post(
        f"/proposals/{proposal_id}/approve", headers=tenant.governor.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def insight_offerings(client: httpx.AsyncClient, tenant: TenantFixture) -> uuid.UUID:
    """Company Insight with approved Services, Advisory and Managed services."""
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    company = str(company_id)
    created = await submit(
        client,
        tenant,
        [
            {
                "type": "concept",
                "companyId": company,
                "parentId": str(root_id),
                "label": "Services",
                "domainKey": "sales",
                "action": "sells",
            },
            *(
                {
                    "type": "concept",
                    "companyId": company,
                    "parentLabel": "Services",
                    "label": label,
                    "domainKey": "sales",
                    "action": "is split into",
                }
                for label in ("Advisory", "Managed services")
            ),
        ],
    )
    for proposal in created:
        await approve(client, tenant, proposal["id"])
    return company_id


async def concept_ids(company_id: uuid.UUID) -> dict[str, str]:
    found = await rows(
        "SELECT label, id FROM ontaix.concept WHERE company_id = :company", company=company_id
    )
    return {r["label"]: str(r["id"]) for r in found}


def test_the_contract_and_the_api_accept_an_attribute_intent() -> None:
    answer = json.loads(spoken(MONTHLY, [attr(MONTHLY, {"candidate": "c2"}, "billing", "monthly")]))
    jsonschema.validate(answer, CONTRACT)
    jsonschema.Draft202012Validator(OUTPUT_SCHEMA).validate(answer)
    [intent] = TeachExtractionAnswer.model_validate(answer).intents
    assert (intent.kind, intent.attribute_name, intent.attribute_value) == (
        "attr",
        "billing",
        "monthly",
    )
    assert intent.object is None and intent.value_type is None


@pytest.mark.parametrize(
    "change",
    [
        {"object": {"newLabel": "Monthly"}},
        {"action": "is billed"},
        {"domainKey": None},
        {"listId": 0},
        {"attributeValue": None},
        {"attributeName": "billing <b>"},
        {"attributeValue": " monthly"},
        {"valueType": "money"},
    ],
)
def test_an_attribute_intent_with_other_fields_is_refused(change: dict) -> None:
    intent = {**attr(MONTHLY, {"candidate": "c2"}, "billing", "monthly"), **change}
    intent = {k: v for k, v in intent.items() if v is not None or k == "domainKey"}
    answer = {"intents": [intent], "unresolved": []}
    assert not jsonschema.Draft202012Validator(CONTRACT).is_valid(answer)
    with pytest.raises(ValidationError):
        TeachExtractionAnswer.model_validate(answer)


def test_a_relation_still_needs_its_object_and_no_attribute_fields() -> None:
    rel = {
        "kind": "rel",
        "subject": {"candidate": "c0"},
        "action": "sells",
        "confidence": 0.9,
        "source": {"start": 0, "end": 5},
    }
    for intent in (rel, {**rel, "object": {"candidate": "c1"}, "attributeName": "billing"}):
        answer = {"intents": [intent], "unresolved": []}
        assert not jsonschema.Draft202012Validator(CONTRACT).is_valid(answer)
        with pytest.raises(ValidationError):
            TeachExtractionAnswer.model_validate(answer)


def test_the_name_is_grounded_on_the_same_stem_and_the_value_word_for_word() -> None:
    whole = (0, len(MONTHLY))
    assert _ground_name("billing", MONTHLY, whole) == "billing"
    assert _ground_name("Billing", MONTHLY, whole) == "billing"
    assert _ground_name("bill", MONTHLY, whole) == "bill"
    assert _ground_name("pricing", "it is priced per day", (0, 20)) == "pricing"
    assert _ground_name("base", "the shop is based in Leeds", (0, 26)) == "base"
    assert _ground_name("headcount", "a headcount of 40", (0, 17)) == "headcount"
    # No other word can be invented, and the name is words alone.
    assert _ground_name("invoicing", MONTHLY, whole) is None
    assert _ground_name("billing frequency", MONTHLY, whole) is None
    assert _ground_name("billing:", MONTHLY, whole) is None
    # Only words inside the source range count.
    assert _ground_name("billing", MONTHLY, (0, 20)) is None

    assert _ground_value("monthly", MONTHLY, whole) == "monthly"
    assert _ground_value("per day", PER_DAY, (0, len(PER_DAY))) == "per day"
    assert _ground_value("Per Day", "Advisory is billed Per  Day", (0, 27)) == "Per Day"
    assert _ground_value("weekly", MONTHLY, whole) is None
    assert _ground_value("per days", PER_DAY, (0, len(PER_DAY))) is None
    assert _ground_value("month", MONTHLY, whole) is None
    assert _ground_value("monthly", MONTHLY, (0, 20)) is None


@pytest.mark.asyncio(loop_scope="session")
async def test_the_owners_billing_sentences_become_taught_attributes(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id = await insight_offerings(client, tenant)
    ids = await concept_ids(company_id)
    session_id = uuid.uuid4()
    fake_llm.answer(
        lambda ctx: spoken(
            MONTHLY,
            [
                attr(
                    MONTHLY,
                    {"candidate": handle(ctx, "Managed services")},
                    "billing",
                    "monthly",
                    explanation="the managed ones: Managed services",
                )
            ],
        ),
        spoken(PER_DAY, [attr(PER_DAY, {"newLabel": "Advisory"}, "billing", "per day")]),
    )

    first = await speak(client, tenant, company_id, MONTHLY, session_id)
    second = await speak(client, tenant, company_id, PER_DAY, session_id)

    assert (first["llmOutcome"], first["outcome"]) == ("used", "understood")
    assert first["unresolved"] == []
    assert first["drafts"] == [
        {
            "origin": "speech",
            "type": "attr",
            "conceptId": ids["Managed services"],
            "name": "billing",
            "attributeType": "text",
            "value": "monthly",
        }
    ]
    assert first["intents"] == [
        {
            "kind": "attr",
            "subject": "Managed services",
            "predicate": "billing",
            "object": "monthly",
            "rule": "llm",
            "subjectResolved": ids["Managed services"],
            "objectResolved": None,
        }
    ]
    assert first["statements"] == ["Managed services billing: monthly"]
    assert first["caption"] == (
        "Managed services billing: monthly. Waiting for your approval on the right."
    )
    assert second["drafts"] == [
        {
            "origin": "speech",
            "type": "attr",
            "conceptId": ids["Advisory"],
            "name": "billing",
            "attributeType": "text",
            "value": "per day",
        }
    ]
    assert second["statements"] == ["Advisory billing: per day"]

    created = await submit(client, tenant, [*first["drafts"], *second["drafts"]])
    assert [p["type"] for p in created] == ["attr", "attr"]
    assert created[0]["title"] == "Managed services.billing"
    assert created[0]["ready"] is True and created[0]["conceptId"] is None
    [pending] = created[0]["artefacts"]["attributes"]
    assert (pending["value"], pending["col"], pending["fill"], pending["state"]) == (
        "monthly",
        None,
        None,
        "proposed",
    )
    for proposal in created:
        decided = await approve(client, tenant, proposal["id"])
        assert decided["artefacts"]["attributes"][0]["state"] == "approved"

    listed = await client.get(
        f"/concepts/{ids['Managed services']}/attributes", headers=tenant.builder.headers
    )
    assert listed.status_code == 200, listed.text
    [billing] = listed.json()
    assert billing["name"] == "billing" and billing["value"] == "monthly"
    assert (billing["col"], billing["fill"], billing["sourceId"]) == (None, None, None)
    scene = await client.get("/scene", headers=tenant.builder.headers)
    advisory = next(c for c in scene.json()["nodes"] if c["id"] == ids["Advisory"])
    assert [(a["name"], a["value"], a["state"]) for a in advisory["attributes"]] == [
        ("billing", "per day", "approved")
    ]
    events = await rows(
        "SELECT payload FROM ontaix.outbox WHERE tenant_id = :tenant"
        " AND aggregate = 'attribute' AND action = 'changed' ORDER BY id",
        tenant=tenant.tenant_id,
    )
    assert [(e["payload"]["attribute"]["state"], e["payload"]["removed"]) for e in events] == [
        ("proposed", False),
        ("proposed", False),
        ("approved", False),
        ("approved", False),
    ]
    assert events[0]["payload"]["attribute"]["value"] == "monthly"


@pytest.mark.asyncio(loop_scope="session")
async def test_an_attribute_the_concept_holds_is_not_drafted_again(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id = await insight_offerings(client, tenant)
    ids = await concept_ids(company_id)
    same, other = MONTHLY, "the managed ones are billed weekly"
    subject = {"newLabel": "Managed services"}
    fake_llm.answer(
        spoken(same, [attr(same, subject, "billing", "monthly")]),
        spoken(same, [attr(same, subject, "billing", "monthly")]),
        spoken(other, [attr(other, subject, "billing", "weekly")]),
    )
    first = await speak(client, tenant, company_id, same)
    await submit(client, tenant, first["drafts"])

    again = await speak(client, tenant, company_id, same)
    changed = await speak(client, tenant, company_id, other)

    assert again["drafts"] == [] and again["unresolved"] == []
    assert again["statements"] == ["Managed services billing: monthly (already in the model)"]
    assert again["intents"][0]["subjectResolved"] == ids["Managed services"]
    assert changed["drafts"] == [] and changed["statements"] == []
    assert changed["unresolved"] == [{"text": other, "reason": "attribute_exists"}]
    refused = await client.post(
        "/proposals/batch", json={"drafts": first["drafts"]}, headers=tenant.builder.headers
    )
    assert refused.status_code == 409 and "duplicate_attribute" in refused.text


@pytest.mark.asyncio(loop_scope="session")
async def test_an_attribute_on_a_concept_the_same_answer_introduces_cites_it_by_label(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    sentence = "Insight offers training and training is billed per session"
    fake_llm.answer(
        spoken(
            sentence,
            [
                {
                    "kind": "rel",
                    "subject": {"candidate": "c0"},
                    "action": "offers",
                    "object": {"newLabel": "Training"},
                    "confidence": 0.9,
                    "span": "Insight offers training",
                    "segment": 0,
                    "source": {"start": 0, "end": 23},
                },
                attr(sentence, {"newLabel": "Training"}, "billing", "per session"),
            ],
        )
    )

    result = await speak(client, tenant, company_id, sentence)

    concept, attribute = result["drafts"]
    assert concept["type"] == "concept" and concept["label"] == "Training"
    assert attribute == {
        "origin": "speech",
        "type": "attr",
        "conceptLabel": "Training",
        "companyId": str(company_id),
        "name": "billing",
        "attributeType": "text",
        "value": "per session",
    }
    assert result["statements"][1] == "Training billing: per session"
    created = await submit(client, tenant, result["drafts"])
    assert created[1]["ready"] is False and created[1]["waitFor"] == "Training"

    rejected = await client.post(
        f"/proposals/{created[0]['id']}/reject", headers=tenant.governor.headers
    )
    assert rejected.status_code == 200, rejected.text
    assert [c["id"] for c in rejected.json()["cascaded"]] == [created[1]["id"]]
    left = await rows(
        "SELECT id FROM ontaix.attribute WHERE tenant_id = :tenant", tenant=tenant.tenant_id
    )
    assert left == []


@pytest.mark.asyncio(loop_scope="session")
async def test_an_attribute_intent_never_creates_a_concept_nor_invents_words(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id = await insight_offerings(client, tenant)
    unknown = "consulting is billed hourly"
    fake_llm.answer(
        spoken(unknown, [attr(unknown, {"newLabel": "Consulting"}, "billing", "hourly")]),
        spoken(PER_DAY, [attr(PER_DAY, {"newLabel": "Advisory"}, "invoicing", "per day")]),
        spoken(PER_DAY, [attr(PER_DAY, {"newLabel": "Advisory"}, "billing", "daily")]),
        spoken(PER_DAY, [attr(PER_DAY, {"newLabel": "Advisory"}, "billing", "per day")]),
    )

    for sentence in (unknown, PER_DAY, PER_DAY):
        result = await speak(client, tenant, company_id, sentence)
        assert result["drafts"] == [] and result["intents"] == []
        assert result["unresolved"] == [{"text": sentence, "reason": "ungrounded_label"}]

    proposed = await speak(client, tenant, company_id, PER_DAY)
    [created] = await submit(client, tenant, proposed["drafts"])
    rejected = await client.post(
        f"/proposals/{created['id']}/reject", headers=tenant.governor.headers
    )
    assert rejected.status_code == 200, rejected.text
    left = await rows(
        "SELECT id FROM ontaix.attribute WHERE tenant_id = :tenant", tenant=tenant.tenant_id
    )
    assert left == []
    removed = await rows(
        "SELECT payload FROM ontaix.outbox WHERE tenant_id = :tenant"
        " AND aggregate = 'attribute' ORDER BY id DESC LIMIT 1",
        tenant=tenant.tenant_id,
    )
    assert removed[0]["payload"]["removed"] is True


@pytest.mark.asyncio(loop_scope="session")
async def test_attribute_drafts_are_one_kind_or_the_other(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    base = {"type": "attr", "conceptId": str(tenant.root_id), "name": "billing"}
    for draft in (
        {**base, "attributeType": "text", "value": "monthly", "col": "a.b", "fill": 3},
        {**base, "attributeType": "id", "value": "monthly"},
        {**base, "attributeType": "text"},
        {**base, "attributeType": "text", "value": "x", "conceptLabel": "Services"},
    ):
        response = await client.post(
            "/proposals/batch", json={"drafts": [draft]}, headers=tenant.builder.headers
        )
        assert response.status_code == 422, (draft, response.text)
    read = {**base, "attributeType": "text", "col": "sap.mara.matnr", "fill": 90}
    response = await client.post(
        "/proposals/batch", json={"drafts": [read]}, headers=tenant.builder.headers
    )
    assert response.status_code == 503


@pytest.mark.asyncio(loop_scope="session")
async def test_the_database_holds_an_attribute_read_or_taught_never_both(
    tenant: TenantFixture,
) -> None:
    insert = (
        "INSERT INTO ontaix.attribute (tenant_id, concept_id, name, type, col, fill, value)"
        " VALUES (:tenant, :concept, :name, CAST(:type AS ontaix.attribute_type), :col, :fill,"
        " :value)"
    )
    base = {"tenant": tenant.tenant_id, "concept": tenant.root_id}
    refused = (
        {"name": "a", "type": "text", "col": "x.y", "fill": 5, "value": "monthly"},
        {"name": "b", "type": "text", "col": None, "fill": None, "value": None},
        {"name": "c", "type": "id", "col": None, "fill": None, "value": "monthly"},
        {"name": "d", "type": "text", "col": "x.y", "fill": None, "value": None},
        {"name": "e", "type": "text", "col": None, "fill": None, "value": ""},
    )
    for values in refused:
        async with db_client.get_session_factory()() as s:
            with pytest.raises(IntegrityError):
                await s.execute(text(insert), {**base, **values})
    async with db_client.get_session_factory()() as s:
        await s.execute(
            text(insert),
            {**base, "name": "f", "type": "number", "col": None, "fill": None, "value": "40"},
        )
        await s.execute(
            text(insert),
            {**base, "name": "g", "type": "id", "col": "x.y", "fill": 80, "value": None},
        )
        await s.rollback()
