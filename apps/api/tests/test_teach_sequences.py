"""A sequence of steps taught in one sentence: the steps are siblings under one parent, and their
order is a `precedes` relation between consecutive steps, never a chain of births. Recorded
answers only; no test reaches a provider."""

from __future__ import annotations

import json

import httpx
import pytest

from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_teach_extraction import add_company, configure, teach
from tests.test_teach_speech import submit

pytestmark = pytest.mark.asyncio(loop_scope="session")

STEPS = "Qualify → Engage Insight AI → Create Salesforce Opp → Scope & Resource"


def rel(subject: dict, action: str, obj: dict, span: str) -> dict:
    start = STEPS.index(span)
    return {
        "kind": "rel",
        "subject": subject,
        "action": action,
        "object": obj,
        "confidence": 0.9,
        "span": span,
        "source": {"start": start, "end": start + len(span)},
    }


def new(label: str) -> dict:
    return {"newLabel": label}


def pairs() -> list[dict]:
    names = STEPS.split(" → ")
    return [
        rel(new(a), "precedes", new(b), f"{a} → {b}")
        for a, b in zip(names, names[1:], strict=False)
    ]


async def test_steps_ordered_by_precedes_are_siblings_under_the_first_steps_parent(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    fake_llm.answer(
        json.dumps(
            {
                "intents": [rel({"candidate": "c0"}, "has", new("Qualify"), "Qualify"), *pairs()],
                "unresolved": [],
            }
        )
    )

    taught = await teach(client, tenant, company_id, STEPS)

    concepts = [d for d in taught["drafts"] if d["type"] == "concept"]
    relations = [d for d in taught["drafts"] if d["type"] == "relation"]
    assert [d["label"] for d in concepts] == [
        "Qualify",
        "Engage Insight AI",
        "Create Salesforce Opp",
        "Scope & Resource",
    ]
    # Every step is born from the company with the first step's action, none from a step.
    assert all(d.get("parentId") == str(root_id) and d["action"] == "has" for d in concepts)
    assert [(d["aLabel"], d["action"], d["bLabel"]) for d in relations] == [
        ("Qualify", "precedes", "Engage Insight AI"),
        ("Engage Insight AI", "precedes", "Create Salesforce Opp"),
        ("Create Salesforce Opp", "precedes", "Scope & Resource"),
    ]
    await submit(client, tenant, taught["drafts"])


async def test_a_chain_that_names_no_parent_puts_its_steps_under_the_company(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    fake_llm.answer(json.dumps({"intents": pairs(), "unresolved": []}))

    taught = await teach(client, tenant, company_id, STEPS)

    concepts = [d for d in taught["drafts"] if d["type"] == "concept"]
    assert len(concepts) == 4
    assert all(d.get("parentId") == str(root_id) for d in concepts)
    assert [d["action"] for d in taught["drafts"] if d["type"] == "relation"] == ["precedes"] * 3
    await submit(client, tenant, taught["drafts"])


async def test_a_step_after_an_existing_step_is_born_beside_it(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    process = {
        "type": "concept",
        "companyId": str(company_id),
        "parentId": str(root_id),
        "label": "Sales process",
        "domainKey": "sales",
        "action": "runs",
    }
    await submit(client, tenant, [process])
    sentence = "Sales process includes Qualify, and Qualify precedes Engage Insight AI"

    def answer(context: dict) -> str:
        c = {x["label"]: x["handle"] for x in context["candidates"]}
        span = "Qualify precedes Engage Insight AI"
        start = sentence.index(span)
        intents = [
            {
                "kind": "rel",
                "subject": {"candidate": c["Sales process"]},
                "action": "includes",
                "object": new("Qualify"),
                "confidence": 0.9,
                "span": "Sales process includes Qualify",
                "source": {"start": 0, "end": 30},
            },
            {
                "kind": "rel",
                "subject": new("Qualify"),
                "action": "precedes",
                "object": new("Engage Insight AI"),
                "confidence": 0.9,
                "span": span,
                "source": {"start": start, "end": start + len(span)},
            },
        ]
        return json.dumps({"intents": intents, "unresolved": []})

    fake_llm.answer(answer)
    taught = await teach(client, tenant, company_id, sentence)

    qualify, engage = (d for d in taught["drafts"] if d["type"] == "concept")
    # The next step shares the named process and its action with the step before it.
    assert qualify["parentId"] == engage["parentId"] != str(root_id)
    assert qualify["action"] == engage["action"] == "includes"
    await submit(client, tenant, taught["drafts"])


async def test_each_step_statement_names_the_new_step(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, _ = await add_company(tenant, "Insight")
    await configure(tenant)
    fake_llm.answer(
        json.dumps(
            {
                "intents": [rel({"candidate": "c0"}, "has", new("Qualify"), "Qualify"), *pairs()],
                "unresolved": [],
            }
        )
    )

    taught = await teach(client, tenant, company_id, STEPS)

    assert taught["statements"] == [
        "Insight has Qualify (new)",
        "Qualify precedes Engage Insight AI (new)",
        "Engage Insight AI precedes Create Salesforce Opp (new)",
        "Create Salesforce Opp precedes Scope & Resource (new)",
    ]
