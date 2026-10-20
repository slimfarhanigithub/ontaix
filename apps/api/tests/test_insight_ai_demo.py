"""The scripted "Insight AI" product demo, replayed step by step over HTTP without a model.

Every request is the one the Studio sends for the demo action: the admin portal's reset and
company removal, the teach bar's spoken and typed sentences, a file dropped on the canvas (its
detection, its sentence import, the whole-document reading that is unavailable without a model
and the sentence-by-sentence fallback), an ontology file, the relation box, the new-concept box,
`Approve all`, and the reset that empties the model again while the companies stay. Spoken and
document sentences go to the model first, so without one they come back `partly_understood`
with the grammar's drafts; typed sentences are read by the grammar alone and are `understood`.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import RoleName, ScopeKind
from app.services import document_extraction_runner_service
from tests.conftest import Persona, TenantFixture
from tests.scoped_users import scoped_user
from tests.test_imports import DOCX_TYPE, docx

pytestmark = pytest.mark.asyncio(loop_scope="session")

COMPANY_NAME = "Insight AI"
RESET = {"type": "change", "changeKind": "reset_model", "payload": {}}

SPOKEN = [
    "Insight AI runs an analytics platform.",
    "An analyst produces an insight report.",
    "A customer receives an insight report.",
]
TYPED = [
    "Insight AI trains a machine learning model.",
    "A data engineer maintains a data pipeline.",
    "Enterprise customer is a customer.",
]
# The paragraphs of "2 - Insight AI overview (drop on canvas).docx", in document order: a title,
# then four headings each followed by its sentences.
OVERVIEW_PARAGRAPHS = [
    "Insight AI company overview",
    "Sales",
    "An account manager owns a customer account.",
    "A customer account signs a contract.",
    "A contract includes a service level agreement.",
    "Delivery",
    "A delivery team runs a client project.",
    "A client project uses a dataset.",
    "A data scientist builds a forecast.",
    "Finance",
    "Finance issues an invoice.",
    "A customer account pays an invoice.",
    "Finance uses a pricing plan.",
    "People",
    "A team lead manages a delivery team.",
    "A data scientist is an employee.",
    "An account manager is an employee.",
]
OVERVIEW_FILE = "2 - Insight AI overview (drop on canvas).docx"
ONTOLOGY_FILE = "3 - Insight AI ontology (drop on canvas).ttl"
# The text of "3 - Insight AI ontology (drop on canvas).ttl".
ONTOLOGY_TURTLE = """@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix ia:   <https://example.org/insight-ai#> .

<https://example.org/insight-ai> a owl:Ontology ;
    rdfs:label "Insight AI offerings and partners"@en .

# Offerings
ia:Offering a owl:Class ; rdfs:label "Offering"@en .
ia:AIPlatform a owl:Class ; rdfs:label "AI platform"@en ; rdfs:subClassOf ia:Offering .
ia:ConsultingService a owl:Class ; rdfs:label "Consulting service"@en ;
    rdfs:subClassOf ia:Offering .
ia:TrainingCourse a owl:Class ; rdfs:label "Training course"@en ; rdfs:subClassOf ia:Offering .
ia:DataProduct a owl:Class ; rdfs:label "Data product"@en ; rdfs:subClassOf ia:Offering .

# Partners
ia:Partner a owl:Class ; rdfs:label "Partner"@en .
ia:CloudProvider a owl:Class ; rdfs:label "Cloud provider"@en ; rdfs:subClassOf ia:Partner .
ia:Reseller a owl:Class ; rdfs:label "Reseller"@en ; rdfs:subClassOf ia:Partner .

# Support
ia:Customer a owl:Class ; rdfs:label "Customer"@en .
ia:SupportTicket a owl:Class ; rdfs:label "Support ticket"@en .

# Relations
ia:hosts a owl:ObjectProperty ; rdfs:label "hosts"@en ;
    rdfs:domain ia:CloudProvider ; rdfs:range ia:AIPlatform .
ia:resells a owl:ObjectProperty ; rdfs:label "resells"@en ;
    rdfs:domain ia:Reseller ; rdfs:range ia:Offering .
ia:raises a owl:ObjectProperty ; rdfs:label "raises"@en ;
    rdfs:domain ia:Customer ; rdfs:range ia:SupportTicket .
ia:concerns a owl:ObjectProperty ; rdfs:label "concerns"@en ;
    rdfs:domain ia:SupportTicket ; rdfs:range ia:Offering .
ia:feeds a owl:ObjectProperty ; rdfs:label "feeds"@en ;
    rdfs:domain ia:DataProduct ; rdfs:range ia:AIPlatform .
"""

# What the demo holds once `Approve all` has run: each concept with its parent (None for a
# concept born from the company root) and every relation as `(a, action, b)`.
FINAL_CONCEPTS: dict[str, str | None] = {
    "Analytics platform": None,
    "Analyst": None,
    "Insight report": "Analyst",
    "Customer": "Insight report",
    "Machine learning model": None,
    "Data engineer": None,
    "Data pipeline": "Data engineer",
    "Enterprise customer": "Customer",
    "Account manager": None,
    "Customer account": "Account manager",
    "Contract": "Customer account",
    "Service level agreement": "Contract",
    "Delivery team": None,
    "Client project": "Delivery team",
    "Dataset": "Client project",
    "Data scientist": None,
    "Forecast": "Data scientist",
    "Finance": None,
    "Invoice": "Finance",
    "Pricing plan": "Finance",
    "Team lead": "Delivery team",
    "Employee": "Data scientist",
    "Offering": None,
    "AI platform": "Offering",
    "Consulting service": "Offering",
    "Training course": "Offering",
    "Data product": "Offering",
    "Partner": None,
    "Cloud provider": "Partner",
    "Reseller": "Partner",
    "Support ticket": None,
    "Dashboard": "Insight report",
    "Executive summary": "Insight report",
}
FINAL_RELATIONS: set[tuple[str, str, str]] = {
    ("Insight AI", "runs", "Analytics platform"),
    ("Insight AI", "has", "Analyst"),
    ("Analyst", "produces", "Insight report"),
    ("Customer", "receives", "Insight report"),
    ("Insight AI", "trains", "Machine learning model"),
    ("Insight AI", "has", "Data engineer"),
    ("Data engineer", "maintains", "Data pipeline"),
    ("Enterprise customer", "is a", "Customer"),
    ("Insight AI", "has", "Account manager"),
    ("Account manager", "owns", "Customer account"),
    ("Customer account", "signs", "Contract"),
    ("Contract", "includes", "Service level agreement"),
    ("Insight AI", "has", "Delivery team"),
    ("Delivery team", "runs", "Client project"),
    ("Client project", "uses", "Dataset"),
    ("Insight AI", "has", "Data scientist"),
    ("Data scientist", "builds", "Forecast"),
    ("Insight AI", "has", "Finance"),
    ("Finance", "issues", "Invoice"),
    ("Customer account", "pays", "Invoice"),
    ("Finance", "uses", "Pricing plan"),
    ("Team lead", "manages", "Delivery team"),
    ("Employee", "is a kind of", "Data scientist"),
    ("Account manager", "is a", "Employee"),
    ("Insight AI", "includes", "Offering"),
    ("AI platform", "is a", "Offering"),
    ("Consulting service", "is a", "Offering"),
    ("Training course", "is a", "Offering"),
    ("Data product", "is a", "Offering"),
    ("Insight AI", "includes", "Partner"),
    ("Cloud provider", "is a", "Partner"),
    ("Reseller", "is a", "Partner"),
    ("Insight AI", "includes", "Support ticket"),
    ("Cloud provider", "hosts", "AI platform"),
    ("Reseller", "resells", "Offering"),
    ("Customer", "raises", "Support ticket"),
    ("Support ticket", "concerns", "Offering"),
    ("Data product", "feeds", "AI platform"),
    ("Analyst", "advises", "Customer"),
    ("Insight report", "published as", "Dashboard"),
    ("Executive summary", "is a", "Insight report"),
}


class Demo:
    """One replay: the company being taught and the requests the Studio sends for it. The
    tenant-wide Builder teaches and the tenant-wide Governor approves."""

    def __init__(self, client: httpx.AsyncClient, tenant: TenantFixture) -> None:
        self.client = client
        self.tenant = tenant
        self.company_id = ""
        self.root_id = ""
        self.session_id = str(uuid.uuid4())

    @property
    def teacher(self) -> Persona:
        return self.tenant.builder

    @property
    def approver(self) -> Persona:
        return self.tenant.governor

    async def add_company(self) -> dict:
        """`+ Add a company` with the `One cell` start; the Studio makes it the taught company
        and the teach bar opens a new teach session for it."""
        created = await self.client.post(
            "/companies",
            json={"name": COMPANY_NAME, "sub": "", "start": "one_cell"},
            headers=self.tenant.admin.headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        self.company_id = body["company"]["id"]
        self.root_id = body["root"]["id"]
        self.session_id = str(uuid.uuid4())
        return body

    def request(self, **source: object) -> dict:
        return {"companyId": self.company_id, "sessionId": self.session_id, **source}

    async def parse_typed(self, text: str) -> dict:
        """A typed sentence: the Studio streams it too, and the result line is what
        `POST /teach/parse` answers."""
        response = await self.client.post(
            "/teach/parse",
            json=self.request(text=text, origin="text"),
            headers=self.teacher.headers,
        )
        assert response.status_code == 200, response.text
        return response.json()

    async def parse_spoken(self, text: str) -> dict:
        """A finished spoken sentence: `POST /teach/parse/stream` as `speech`; the result line
        is the parse result."""
        response = await self.client.post(
            "/teach/parse/stream",
            json=self.request(text=text, origin="speech"),
            headers=self.teacher.headers,
        )
        assert response.status_code == 200, response.text
        lines = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        assert lines[-1]["type"] == "result", lines
        return lines[-1]["result"]

    async def parse_cited(self, import_id: str, index: int) -> dict:
        """One stored import sentence, taught the way the Studio teaches a document sentence by
        sentence."""
        response = await self.client.post(
            "/teach/parse",
            json=self.request(importRef={"importId": import_id, "sentenceIndex": index}),
            headers=self.teacher.headers,
        )
        assert response.status_code == 200, response.text
        return response.json()

    async def batch(self, result: dict) -> list[dict]:
        """The drafts of one parse, proposed as one batch, linked to the parse."""
        if not result["drafts"]:
            return []
        body: dict = {"drafts": result["drafts"]}
        if result.get("parseId"):
            body["parseId"] = result["parseId"]
        created = await self.client.post(
            "/proposals/batch", json=body, headers=self.teacher.headers
        )
        assert created.status_code == 202, created.text
        return created.json()

    async def propose(self, draft: dict) -> dict:
        created = await self.client.post("/proposals", json=draft, headers=self.teacher.headers)
        assert created.status_code == 202, created.text
        return created.json()

    async def approve(self, proposal: dict, headers: dict[str, str] | None = None) -> dict:
        """The panel's `Approve`, at the revision the panel shows."""
        decided = await self.client.post(
            f"/proposals/{proposal['id']}/approve?expectedRevision={proposal['revision']}",
            headers=headers or self.approver.headers,
        )
        assert decided.status_code == 200, decided.text
        return decided.json()

    async def open_proposals(self) -> list[dict]:
        listed = await self.client.get("/proposals?pageSize=200", headers=self.approver.headers)
        assert listed.status_code == 200, listed.text
        return listed.json()["items"]

    async def scene(self) -> dict:
        response = await self.client.get("/scene", headers=self.approver.headers)
        assert response.status_code == 200, response.text
        return response.json()

    async def concepts(self) -> dict[str, dict]:
        """The live concepts of the taught company by label, the root left out."""
        scene = await self.scene()
        return {
            n["label"]: n
            for n in scene["nodes"]
            if n["companyId"] == self.company_id and n["kind"] != "root"
        }

    async def parents(self) -> dict[str, str | None]:
        """Each concept's parent label; None under the company root."""
        concepts = await self.concepts()
        by_id = {n["id"]: label for label, n in concepts.items()}
        return {label: by_id.get(n["parentId"]) for label, n in concepts.items()}

    async def relations(self) -> set[tuple[str, str, str]]:
        """`(a, action, b)` of every non-binding link whose ends are in the taught company."""
        scene = await self.scene()
        labels = {n["id"]: n["label"] for n in scene["nodes"]}
        mine = {n["id"] for n in scene["nodes"] if n["companyId"] == self.company_id}
        return {
            (labels[link["aId"]], link["label"], labels[link["bId"]])
            for link in scene["links"]
            if link.get("kind") != "bind" and link["aId"] in mine and link["bId"] in mine
        }


def births(result: dict) -> list[tuple[str, str, str | None, str | None]]:
    """`(label, birth action, parent id, parent label)` of each concept or spec draft."""
    return [
        (d["label"], d.get("action", "is a"), d.get("parentId"), d.get("parentLabel"))
        for d in result["drafts"]
        if d["type"] in ("concept", "spec")
    ]


def relation_ends(result: dict) -> list[tuple[str | None, str, str | None]]:
    return [
        (d.get("aId"), d["action"], d.get("bId"))
        for d in result["drafts"]
        if d["type"] == "relation"
    ]


def degraded_by_missing_model(result: dict, text: str) -> None:
    """A spoken or document sentence without a model: the grammar's drafts, marked degraded."""
    assert result["outcome"] == "partly_understood", result
    assert result["degraded"] is True and result["llmOutcome"] == "not_configured"
    assert result["unresolved"] == [{"text": text, "reason": "model_unavailable"}]


async def test_the_insight_ai_demo_replays_end_to_end(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    demo = Demo(client, tenant)
    tenant_owner = await scoped_user(session, tenant, RoleName.OWNER, ScopeKind.TENANT)

    # A previous run left Insight AI taught: one proposal waits, so the reset has work to do.
    await demo.add_company()
    await demo.batch(await demo.parse_spoken(SPOKEN[0]))

    # Step 0, Entities > Reset model... > Propose reset. Only an Administrator proposes it: a
    # company Owner and a tenant-wide Owner are refused.
    for headers in (tenant.owner.headers, tenant_owner):
        refused = await client.post("/proposals", json=RESET, headers=headers)
        assert refused.status_code == 403, refused.text
    reset = await client.post("/proposals", json=RESET, headers=tenant.admin.headers)
    assert reset.status_code == 202, reset.text
    reset = reset.json()
    assert (reset["heading"], reset["title"], reset["ready"]) == ("Change", "Reset the model", True)
    assert reset["html"] == (
        "Remove <b>1 concept</b> and 1 relation from every company, and reject 1 open proposal"
    )
    # `Approve all` approves the waiting concept and leaves the reset pending; its own
    # `Approve` decides it, here by the tenant-wide Owner.
    bulk = await client.post("/proposals/approve-all", headers=tenant.governor.headers)
    assert bulk.status_code == 200, bulk.text
    assert (bulk.json()["approved"], bulk.json()["remaining"]) == (1, 1)
    still = await client.get(f"/proposals/{reset['id']}", headers=tenant.governor.headers)
    assert still.json()["state"] == "pending"
    decided = await demo.approve(reset, tenant_owner)
    assert decided["proposal"]["state"] == "approved"
    assert await demo.concepts() == {}

    # Step 0, Companies > Remove > Propose removal. The impact is read first; the removal is a
    # proposal of the company scope, which an Administrator may not make and a tenant-wide
    # Owner proposes and approves.
    impact = await client.post(
        "/deletion-impact",
        json={"companyId": demo.company_id, "wholeCompany": True},
        headers=tenant_owner,
    )
    assert impact.status_code == 200, impact.text
    assert (impact.json()["concepts"], impact.json()["relations"]) == (0, 0)
    refused = await client.delete(f"/companies/{demo.company_id}", headers=tenant.admin.headers)
    assert refused.status_code == 403, refused.text
    removal = await client.delete(f"/companies/{demo.company_id}", headers=tenant_owner)
    assert removal.status_code == 202, removal.text
    assert removal.json()["heading"] == "Change"
    assert removal.json()["html"].startswith("Remove <b>Insight AI</b> from the portfolio")
    removed = await demo.approve(removal.json(), tenant_owner)
    assert removed["proposal"]["state"] == "approved"
    gone = await client.get(f"/companies/{demo.company_id}", headers=tenant.governor.headers)
    assert gone.status_code == 404

    # Step 0, + Add a company. Only an Administrator adds one.
    for headers in (tenant.owner.headers, tenant_owner):
        refused = await client.post(
            "/companies",
            json={"name": COMPANY_NAME, "sub": "", "start": "one_cell"},
            headers=headers,
        )
        assert refused.status_code == 403, refused.text
    created = await demo.add_company()
    assert created["company"]["name"] == COMPANY_NAME
    assert created["root"]["label"] == COMPANY_NAME
    assert created["proposals"] == []
    scene = await demo.scene()
    assert [(c["name"], c["isHome"]) for c in scene["companies"]] == [
        (tenant.company_name, True),
        (COMPANY_NAME, False),
    ]

    # Step 1, three spoken sentences, one at a time: the next is parsed once the previous one's
    # drafts are proposed, as the teach bar's speech queue does.
    results = []
    for text in SPOKEN:
        result = await demo.parse_spoken(text)
        degraded_by_missing_model(result, text)
        made = await demo.batch(result)
        assert {p["origin"] for p in made} == {"speech"}
        results.append(result)
    assert [r["statements"] for r in results] == [
        ["Insight AI runs Analytics platform (new)"],
        ["Analyst produces Insight report (both new)"],
        ["Customer (new) receives Insight report"],
    ]
    assert births(results[0]) == [("Analytics platform", "runs", demo.root_id, None)]
    assert births(results[1]) == [
        ("Analyst", "has", demo.root_id, None),
        ("Insight report", "produces", None, "Analyst"),
    ]
    insight_report = (await demo.concepts())["Insight report"]["id"]
    assert births(results[2]) == [("Customer", "receives", insight_report, None)]

    # Step 2, three typed sentences: the grammar alone understands each of them.
    results = []
    for text in TYPED:
        result = await demo.parse_typed(text)
        assert result["outcome"] == "understood", result
        assert result["degraded"] is False and result["unresolved"] == []
        await demo.batch(result)
        results.append(result)
    assert [r["statements"] for r in results] == [
        ["Insight AI trains Machine learning model (new)"],
        ["Data engineer maintains Data pipeline (both new)"],
        ["Enterprise customer is a Customer"],
    ]
    assert births(results[0]) == [("Machine learning model", "trains", demo.root_id, None)]
    # Neither concept existed: Data engineer is born from the company root with `has` and Data
    # pipeline from it.
    assert births(results[1]) == [
        ("Data engineer", "has", demo.root_id, None),
        ("Data pipeline", "maintains", None, "Data engineer"),
    ]
    customer = (await demo.concepts())["Customer"]["id"]
    assert results[2]["drafts"] == [
        {
            "origin": "text",
            "type": "spec",
            "companyId": demo.company_id,
            "parentId": customer,
            "label": "Enterprise customer",
            "rule": "",
            "domainKey": "production",
            "caption": "Customer divides: Enterprise customer inherits everything Customer is.",
        }
    ]
    assert await demo.parents() == {
        "Analytics platform": None,
        "Analyst": None,
        "Insight report": "Analyst",
        "Customer": "Insight report",
        "Machine learning model": None,
        "Data engineer": None,
        "Data pipeline": "Data engineer",
        "Enterprise customer": "Customer",
    }

    # Step 3, the Word file dropped on the canvas: detected as a document, imported, read whole
    # (the job fails without a model), then taught sentence by sentence.
    data = docx(OVERVIEW_PARAGRAPHS)
    detection = await client.post(
        "/import/detect",
        files={"file": (OVERVIEW_FILE, data, DOCX_TYPE)},
        headers=demo.teacher.headers,
    )
    assert detection.status_code == 200, detection.text
    assert detection.json() == {"kind": "document", "format": None, "mediaType": DOCX_TYPE}
    imported = await client.post(
        "/import/sentences",
        files={"file": (OVERVIEW_FILE, data, DOCX_TYPE)},
        data={"mediaType": DOCX_TYPE},
        headers=demo.teacher.headers,
    )
    assert imported.status_code == 200, imported.text
    imported = imported.json()
    assert imported["fileName"] == OVERVIEW_FILE
    # The four headings are shorter than a sentence; the title is kept as one.
    assert imported["sentences"] == [p for p in OVERVIEW_PARAGRAPHS if len(p) >= 13]
    assert len(imported["sentences"]) == 13 and imported["skipped"] == 4
    job = await client.post(
        f"/import/{imported['importId']}/extraction",
        json={"companyId": demo.company_id},
        headers=demo.teacher.headers,
    )
    assert job.status_code == 202, job.text
    await document_extraction_runner_service.run_once()
    status = await client.get(f"/extractions/{job.json()['id']}", headers=demo.teacher.headers)
    assert (status.json()["state"], status.json()["failureReason"]) == (
        "failed",
        "not_configured",
    ), status.text
    before = len(await demo.open_proposals())
    results = []
    for index in range(len(imported["sentences"])):
        result = await demo.parse_cited(imported["importId"], index)
        made = await demo.batch(result)
        assert all(p["origin"] == "document" for p in made)
        results.append(result)
    title, *sentences = results
    assert title["outcome"] == "not_understood" and title["drafts"] == []
    for text, result in zip(imported["sentences"][1:], sentences, strict=True):
        degraded_by_missing_model(result, text)
    assert [r["statements"] for r in sentences] == [
        ["Account manager owns Customer account (both new)"],
        ["Customer account signs Contract (new)"],
        ["Contract includes Service level agreement (new)"],
        ["Delivery team runs Client project (both new)"],
        ["Client project uses Dataset (new)"],
        ["Data scientist builds Forecast (both new)"],
        ["Finance issues Invoice (both new)"],
        ["Customer account pays Invoice"],
        ["Finance uses Pricing plan (new)"],
        ["Team lead (new) manages Delivery team"],
        ["Data scientist is a kind of Employee (new)"],
        ["Account manager is a Employee"],
    ]
    assert [len(r["drafts"]) for r in sentences] == [2, 1, 1, 2, 1, 2, 2, 1, 1, 1, 1, 1]
    assert len(await demo.open_proposals()) - before == 16
    concepts = await demo.concepts()
    assert relation_ends(sentences[7]) == [
        (concepts["Customer account"]["id"], "pays", concepts["Invoice"]["id"])
    ]
    assert relation_ends(sentences[11]) == [
        (concepts["Account manager"]["id"], "is a", concepts["Employee"]["id"])
    ]

    # Step 3, the Turtle file dropped on the canvas: detected as an ontology, mapped under the
    # company root and proposed whole.
    turtle = ONTOLOGY_TURTLE.encode()
    detection = await client.post(
        "/import/detect",
        files={"file": (ONTOLOGY_FILE, turtle, "application/octet-stream")},
        headers=demo.teacher.headers,
    )
    assert detection.status_code == 200, detection.text
    assert detection.json() == {"kind": "ontology", "format": "turtle", "mediaType": "text/plain"}
    mapped = await client.post(
        "/ontology-imports",
        files={"file": (ONTOLOGY_FILE, turtle, "application/octet-stream")},
        data={
            "companyId": demo.company_id,
            "languages": "en-GB,en",
            "individuals": "skip",
            "format": "turtle",
        },
        headers=demo.teacher.headers,
    )
    assert mapped.status_code == 200, mapped.text
    mapped = mapped.json()
    assert [
        (d["type"], d.get("label") or d["action"], d.get("parentId") or d.get("parentLabel"))
        for d in mapped["drafts"]
    ] == [
        ("concept", "Offering", demo.root_id),
        ("spec", "AI platform", "Offering"),
        ("concept", "Partner", demo.root_id),
        ("spec", "Cloud provider", "Partner"),
        ("spec", "Consulting service", "Offering"),
        ("spec", "Data product", "Offering"),
        ("spec", "Reseller", "Partner"),
        ("concept", "Support ticket", demo.root_id),
        ("spec", "Training course", "Offering"),
        ("relation", "concerns", None),
        ("relation", "feeds", None),
        ("relation", "hosts", None),
        ("relation", "raises", None),
        ("relation", "resells", None),
    ]
    assert all(d["action"] == "includes" for d in mapped["drafts"] if d["type"] == "concept")
    raises = next(d for d in mapped["drafts"] if d.get("action") == "raises")
    assert (raises["aId"], raises["bLabel"]) == (concepts["Customer"]["id"], "Support ticket")
    assert mapped["skipped"] == [
        {
            "source": "https://example.org/insight-ai#Customer",
            "label": "Customer",
            "reason": "reused_existing",
        }
    ]
    proposed = await client.post(
        f"/ontology-imports/{mapped['ontologyImportId']}/proposals",
        json={"indexes": list(range(len(mapped["drafts"])))},
        headers=demo.teacher.headers,
    )
    assert proposed.status_code == 202, proposed.text
    assert len(proposed.json()) == 14

    # Step 3, Analyst dragged onto Customer with the action "advises".
    concepts = await demo.concepts()
    dragged = await demo.propose(
        {
            "type": "relation",
            "aId": concepts["Analyst"]["id"],
            "bId": concepts["Customer"]["id"],
            "action": "advises",
            "caption": "Analyst advises Customer.",
        }
    )
    assert (dragged["heading"], dragged["title"]) == ("Relation", "Analyst advises Customer")

    # Step 4, Insight report > More actions > Grow a concept from it: Dashboard, "published as",
    # Propose; then the Specialisation button for a second one.
    report = concepts["Insight report"]
    grown = await demo.propose(
        {
            "type": "concept",
            "companyId": demo.company_id,
            "parentId": report["id"],
            "label": "Dashboard",
            "domainKey": report["domainKey"],
            "action": "published as",
            "caption": "Dashboard is kept in Production.",
        }
    )
    assert grown["heading"] == "New concept · Production"
    assert grown["html"] == "<b>Dashboard</b> <i>· Insight report <b>published as</b> Dashboard</i>"
    specialised = await demo.propose(
        {
            "type": "spec",
            "companyId": demo.company_id,
            "parentId": report["id"],
            "label": "Executive summary",
            "rule": "",
            "domainKey": report["domainKey"],
            "caption": (
                "Insight report divides: Executive summary inherits everything Insight report is."
            ),
        }
    )
    assert specialised["heading"] == "Specialisation · Production"
    assert specialised["html"] == "<b>Executive summary</b> <i>is a Insight report</i>"

    # Step 5, Approve all: one call approves every pending proposal, parents first.
    pending = await demo.open_proposals()
    assert len(pending) == 41
    # Ready at once: the concepts born from the company root; the rest wait for their parents.
    assert {p["title"] for p in pending if p["ready"]} == {
        label for label, parent in FINAL_CONCEPTS.items() if parent is None
    }
    bulk = await client.post("/proposals/approve-all", headers=tenant.governor.headers)
    assert bulk.status_code == 200, bulk.text
    # The pass count depends on the order the pending proposals are walked in, which is not fixed.
    result = bulk.json()
    assert result.pop("rounds") >= 2
    assert result == {
        "approved": 41,
        "rejected": 0,
        "remaining": 0,
        "caption": "All pending proposals are now part of the model.",
    }
    assert await demo.open_proposals() == []
    assert await demo.parents() == FINAL_CONCEPTS
    assert all(n["pending"] is False for n in (await demo.concepts()).values())
    assert await demo.relations() == FINAL_RELATIONS

    # The reset at the end: the concepts and relations go, the companies stay.
    reset = await client.post("/proposals", json=RESET, headers=tenant.admin.headers)
    assert reset.status_code == 202, reset.text
    assert reset.json()["html"] == (
        "Remove <b>33 concepts</b> and 41 relations from every company, and reject 0 open proposals"
    )
    decided = await demo.approve(reset.json())
    assert decided["proposal"]["state"] == "approved"
    scene = await demo.scene()
    assert {n["kind"] for n in scene["nodes"]} == {"root"}
    assert [link for link in scene["links"] if link.get("kind") != "bind"] == []
    assert [c["name"] for c in scene["companies"]] == [tenant.company_name, COMPANY_NAME]
    assert await demo.open_proposals() == []
