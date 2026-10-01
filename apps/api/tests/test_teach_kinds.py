"""Kinds against members: "N can be X or Y" and "either X or Y" name kinds of N, drafted as
`spec` (an "is a" child), while "can be in Y" names a group N includes.

Recorded model answers only; no test reaches a provider. The grammar never reads a "can be"
list: it leaves the sentence to the model.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.services.teach_extraction_service import examples_for
from app.utilities.teach_parser import ParsedIntent, understand
from tests.conftest import TenantFixture
from tests.llm_fakes import FakeLlmClient
from tests.test_teach_extraction import add_company, configure
from tests.test_teach_speech import speak, submit

# The owner's sentence as the browser heard it.
OWNER = (
    "insight has employees they can be consultants or engineers they can have skills "
    "either soft skills or technical skills"
)
SEGMENTS = [(0, 21), (22, 58), (59, 118)]


def spans(text: str, span: str) -> dict:
    start = text.index(span)
    return {"start": start, "end": start + len(span)}


def rel(text: str, subject: dict, obj: dict, action: str, span: str, segment: int) -> dict:
    return {
        "kind": "rel",
        "subject": subject,
        "object": obj,
        "action": action,
        "confidence": 0.9,
        "span": span,
        "source": spans(text, span),
        "segment": segment,
    }


def spec(text: str, child: dict, parent: dict, span: str, segment: int) -> dict:
    return {
        "kind": "spec",
        "subject": child,
        "object": parent,
        "confidence": 0.9,
        "span": span,
        "source": spans(text, span),
        "segment": segment,
    }


def answer(text: str, segments: list[tuple[int, int]], *intents: dict) -> str:
    return json.dumps(
        {
            "intents": list(intents),
            "unresolved": [],
            "segments": [{"index": i, "start": s, "end": e} for i, (s, e) in enumerate(segments)],
        }
    )


def tree(result: dict, root_id: uuid.UUID) -> list[tuple]:
    """(parent, link, label) per draft: a spec draft is an "is a" child of its parent."""

    def parent(d: dict) -> str:
        if d.get("parentId") == str(root_id):
            return "root"
        return d.get("parentLabel") or d["parentId"]

    return [(parent(d), d.get("action", "is a"), d["label"]) for d in result["drafts"]]


@pytest.mark.asyncio(loop_scope="session")
async def test_the_owners_sentence_gives_kinds_of_employees_and_of_skills(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    employees, skills = {"newLabel": "Employees"}, {"newLabel": "Skills"}
    kinds = "they can be consultants or engineers"
    either = "either soft skills or technical skills"
    fake_llm.answer(
        answer(
            OWNER,
            SEGMENTS,
            rel(OWNER, {"candidate": "c0"}, employees, "has", "insight has employees", 0),
            spec(OWNER, {"newLabel": "Consultants"}, employees, kinds, 1),
            spec(OWNER, {"newLabel": "Engineers"}, employees, kinds, 1),
            rel(OWNER, employees, skills, "has", "they can have skills", 2),
            spec(OWNER, {"newLabel": "Soft skills"}, skills, either, 2),
            spec(OWNER, {"newLabel": "Technical skills"}, skills, either, 2),
        )
    )

    result = await speak(client, tenant, company_id, OWNER, uuid.uuid4())

    assert (result["extractor"], result["llmOutcome"], result["degraded"]) == ("llm", "used", False)
    assert tree(result, root_id) == [
        ("root", "has", "Employees"),
        ("Employees", "is a", "Consultants"),
        ("Employees", "is a", "Engineers"),
        ("Employees", "has", "Skills"),
        ("Skills", "is a", "Soft skills"),
        ("Skills", "is a", "Technical skills"),
    ]
    assert [d["type"] for d in result["drafts"]] == [
        "concept",
        "spec",
        "spec",
        "concept",
        "spec",
        "spec",
    ]
    assert "Consultants is a Employees" in result["statements"]
    assert not any("includes" in s for s in result["statements"])
    created = await submit(client, tenant, result["drafts"])
    assert len(created) == 6


@pytest.mark.asyncio(loop_scope="session")
async def test_can_be_in_a_group_stays_a_member_while_can_be_a_kind_is_a_child(
    client: httpx.AsyncClient, tenant: TenantFixture, fake_llm: FakeLlmClient
) -> None:
    company_id, root_id = await add_company(tenant, "Insight")
    await configure(tenant)
    await submit(
        client,
        tenant,
        [
            {
                "type": "concept",
                "companyId": str(company_id),
                "parentId": str(root_id),
                "label": "Employees",
                "domainKey": "people",
                "action": "has",
            }
        ],
    )
    said = "these employees can be consultants and can be in sales"

    def cite_employees(data: dict) -> str:
        handle = next(c["handle"] for c in data["candidates"] if c["label"] == "Employees")
        whole = [(0, len(said))]
        return answer(
            said,
            whole,
            spec(
                said,
                {"newLabel": "Consultants"},
                {"candidate": handle},
                "these employees can be consultants",
                0,
            ),
            rel(
                said, {"candidate": handle}, {"newLabel": "Sales"}, "includes", "can be in sales", 0
            ),
        )

    fake_llm.answer(cite_employees)

    result = await speak(client, tenant, company_id, said, uuid.uuid4())

    assert result["llmOutcome"] == "used"
    by_label = {d["label"]: d for d in result["drafts"]}
    assert by_label["Consultants"]["type"] == "spec"
    assert by_label["Consultants"]["parentId"] == by_label["Sales"]["parentId"]
    assert by_label["Sales"]["type"] == "concept" and by_label["Sales"]["action"] == "includes"
    assert "Consultants is a Employees" in result["statements"]


def test_the_owners_sentence_retrieves_the_kinds_example() -> None:
    chosen = examples_for(OWNER, "speech")
    assert any(e["input"]["sentence"] == OWNER for e in chosen)
    kinds = next(e for e in chosen if e["input"]["sentence"] == OWNER)
    assert [i["kind"] for i in kinds["output"]["intents"]] == [
        "rel",
        "spec",
        "spec",
        "rel",
        "spec",
        "spec",
    ]


def test_the_grammar_leaves_can_be_lists_to_the_model() -> None:
    assert understand("they can be consultants or engineers") == []
    assert understand("engineers are employees") == [
        ParsedIntent("spec", subj="engineer", obj="employee")
    ]
    assert understand("the team includes Sam") == [
        ParsedIntent("rel", subj="team", obj="sam", pred="includes")
    ]
