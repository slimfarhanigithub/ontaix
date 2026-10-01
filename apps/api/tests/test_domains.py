"""Tenant domains: the list, creating and editing a domain through proposals, and the custom
domain keys the model answers may carry."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm.teach_extraction_answer import TeachExtractionAnswer
from app.models.storage.base import RoleName, ScopeKind
from app.models.storage.outbox import Outbox
from app.models.storage.tenant_domain_revision import TenantDomainRevision
from app.repositories import tenant_domain_repository
from tests.conftest import Persona, TenantFixture
from tests.role_grants import persona_with_role
from tests.test_proposals import add_company, approved, propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")

TEMPLATE_KEYS = [
    "production",
    "supply",
    "sales",
    "logistics",
    "quality",
    "maintenance",
    "finance",
    "people",
    "engineering",
]


async def propose_domain(
    client: httpx.AsyncClient,
    persona: Persona,
    name: str,
    color: str = "#336699",
    owner: str | None = "Ann",
) -> httpx.Response:
    body: dict = {"name": name, "color": color}
    if owner is not None:
        body["owner"] = owner
    return await client.post("/domains", json=body, headers=persona.headers)


async def approve(client: httpx.AsyncClient, persona: Persona, proposal_id: str) -> httpx.Response:
    return await client.post(f"/proposals/{proposal_id}/approve", headers=persona.headers)


async def created_domain(
    client: httpx.AsyncClient, tenant: TenantFixture, name: str, color: str = "#336699"
) -> dict:
    """Propose a domain as the tenant Builder, approve it as the Governor, return it."""
    proposed = await propose_domain(client, tenant.builder, name, color)
    assert proposed.status_code == 202, proposed.text
    decided = await approve(client, tenant.governor, proposed.json()["id"])
    assert decided.status_code == 200, decided.text
    listed = await client.get("/domains", headers=tenant.builder.headers)
    return next(d for d in listed.json() if d["name"] == name)


async def events(session: AsyncSession, tenant: TenantFixture, aggregate: str) -> list[Outbox]:
    return list(
        await session.scalars(
            select(Outbox)
            .where(Outbox.tenant_id == tenant.tenant_id, Outbox.aggregate == aggregate)
            .order_by(Outbox.id)
        )
    )


async def test_get_domains_lists_the_templates_in_ring_order_for_any_role(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.get("/domains", headers=tenant.owner.headers)

    assert response.status_code == 200, response.text
    domains = response.json()
    assert [d["key"] for d in domains] == TEMPLATE_KEYS
    assert [d["position"] for d in domains] == list(range(9))
    assert all(d["template"] is True and d["revision"] == 0 for d in domains)
    assert all(d["color"] == d["defaultColor"] for d in domains)
    sales = next(d for d in domains if d["key"] == "sales")
    assert sales["name"] == "Sales"
    assert (await client.get("/domains", headers=tenant.outsider.headers)).status_code == 403


async def test_create_domain_is_proposed_at_tenant_scope(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await propose_domain(client, tenant.builder, "Customer care")

    assert response.status_code == 202, response.text
    proposal = response.json()
    assert proposal["type"] == "change"
    assert proposal["changeKind"] == "create_domain"
    assert proposal["companyId"] is None and proposal["domainProductId"] is None
    assert proposal["title"] == "New domain Customer care"
    assert proposal["heading"] == "Change"
    assert proposal["color"] == "#336699"
    assert "Customer care" in proposal["html"]
    assert (await propose_domain(client, tenant.owner, "Retail")).status_code == 403
    assert (await propose_domain(client, tenant.outsider, "Retail")).status_code == 403
    assert (await propose_domain(client, tenant.admin, "Retail")).status_code == 403


async def test_create_domain_approval_adds_the_domain_for_every_company(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    proposed = (await propose_domain(client, tenant.builder, "Customer care")).json()
    assert (await approve(client, tenant.owner, proposed["id"])).status_code == 403

    decided = await approve(client, tenant.governor, proposed["id"])

    assert decided.status_code == 200, decided.text
    assert decided.json()["audit"]["what"] == "New domain Customer care"
    assert decided.json()["audit"]["companyIds"] == []
    domains = (await client.get("/domains", headers=tenant.builder.headers)).json()
    domain = domains[-1]
    assert domain == {
        "key": "customer_care",
        "name": "Customer care",
        "owner": "Ann",
        "color": "#336699",
        "defaultColor": "#336699",
        "template": False,
        "position": 9,
        "revision": 0,
    }
    revisions = list(
        await session.scalars(
            select(TenantDomainRevision).where(
                TenantDomainRevision.tenant_id == tenant.tenant_id,
                TenantDomainRevision.key == "customer_care",
            )
        )
    )
    assert [(r.revision, r.name, r.color, r.owner) for r in revisions] == [
        (0, "Customer care", "#336699", "Ann")
    ]
    assert revisions[0].proposal_id == uuid.UUID(proposed["id"])
    changed = await events(session, tenant, "domain")
    assert [(e.action, e.payload["created"], e.company_ids) for e in changed] == [
        ("changed", True, [])
    ]
    assert changed[0].payload["domain"]["key"] == "customer_care"

    # The home company has no product for it until its first concept joins it.
    home = await client.get(f"/companies/{tenant.company_id}", headers=tenant.builder.headers)
    assert "customer_care" not in {p["key"] for p in home.json()["domainProducts"]}
    concept = await approved(client, tenant, "Help desk", domain_key="customer_care")
    assert concept["domainKey"] == "customer_care" and concept["color"] == "#336699"
    home = await client.get(f"/companies/{tenant.company_id}", headers=tenant.builder.headers)
    product = next(p for p in home.json()["domainProducts"] if p["key"] == "customer_care")
    assert product["name"] == "Customer care" and product["revision"] == 1
    assert product["counts"]["members"] == 1
    # A company added afterwards holds a product for it from the start.
    other = await add_company(client, tenant, "Later")
    assert "customer_care" in {p["key"] for p in other["company"]["domainProducts"]}
    scene = (await client.get("/scene", headers=tenant.builder.headers)).json()
    assert scene["appearance"]["colors"]["customer_care"] == "#336699"
    assert scene["appearance"]["defaults"]["colors"]["customer_care"] == "#336699"


async def test_create_domain_refuses_taken_names_and_bad_text(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    duplicate = await propose_domain(client, tenant.builder, "SALES")
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "duplicate_label"
    assert (await propose_domain(client, tenant.builder, "Care <b>")).status_code == 422
    assert (await propose_domain(client, tenant.builder, " Care")).status_code == 422
    assert (
        await propose_domain(client, tenant.builder, "Care", color="#ABCDEF")
    ).status_code == 422
    assert (await propose_domain(client, tenant.builder, "Care", owner="x" * 61)).status_code == 422
    no_owner = await propose_domain(client, tenant.builder, "Care", owner=None)
    assert no_owner.status_code == 202, no_owner.text

    # The name is re-checked when the proposal is approved.
    first = (await propose_domain(client, tenant.builder, "Retail")).json()
    second = (await propose_domain(client, tenant.builder, "retail")).json()
    assert (await approve(client, tenant.governor, first["id"])).status_code == 200
    late = await approve(client, tenant.governor, second["id"])
    assert late.status_code == 409 and late.json()["code"] == "duplicate_label"


async def test_create_domain_refuses_the_65th_domain(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    for n in range(9, 64):
        await tenant_domain_repository.create(
            session,
            tenant.tenant_id,
            key=f"custom_{n}",
            name=f"Custom {n}",
            owner="",
            color="#101010",
            position=n,
            proposal_id=None,
        )
    await session.commit()
    assert len((await client.get("/domains", headers=tenant.builder.headers)).json()) == 64

    response = await propose_domain(client, tenant.builder, "One too many")

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "domain_limit"


async def test_edit_domain_recolours_every_concept_of_the_domain_in_every_company(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    other = (await add_company(client, tenant, "Second"))["company"]
    home_deal = await approved(client, tenant, "Home deal", domain_key="sales")
    home_press = await approved(client, tenant, "Home press", domain_key="production")
    other_deal = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": other["id"],
            "parentId": other["rootId"],
            "label": "Other deal",
            "domainKey": "sales",
            "action": "has",
        },
        headers=tenant.builder.headers,
    )
    assert other_deal.status_code == 202, other_deal.text
    assert (await approve(client, tenant.governor, other_deal.json()["id"])).status_code == 200
    old_color = home_deal["color"]

    proposed = await client.patch(
        "/domains/sales",
        json={"name": "Commercial", "color": "#123456", "owner": "Bob"},
        headers=tenant.builder.headers,
    )

    assert proposed.status_code == 202, proposed.text
    proposal = proposed.json()
    assert proposal["changeKind"] == "edit_domain"
    assert proposal["companyId"] is None and proposal["domainProductId"] is None
    assert proposal["title"] == "Edit domain Sales"
    assert "Commercial" in proposal["html"] and "#123456" in proposal["html"]
    assert (await approve(client, tenant.owner, proposal["id"])).status_code == 403

    decided = await approve(client, tenant.governor, proposal["id"])

    assert decided.status_code == 200, decided.text
    domains = (await client.get("/domains", headers=tenant.owner.headers)).json()
    sales = next(d for d in domains if d["key"] == "sales")
    assert sales["name"] == "Commercial" and sales["owner"] == "Bob"
    assert sales["color"] == "#123456" and sales["revision"] == 1
    assert sales["template"] is True and sales["defaultColor"] == old_color
    scene = (await client.get("/scene", headers=tenant.governor.headers)).json()
    assert scene["appearance"]["colors"]["sales"] == "#123456"
    assert scene["appearance"]["defaults"]["colors"]["sales"] == old_color
    sales_nodes = [n for n in scene["nodes"] if n["domainKey"] == "sales"]
    assert {n["companyId"] for n in sales_nodes} == {str(tenant.company_id), other["id"]}
    assert all(n["color"] == "#123456" for n in sales_nodes)
    press = next(n for n in scene["nodes"] if n["id"] == home_press["id"])
    assert press["color"] == home_press["color"]
    for company in scene["companies"]:
        product = next(p for p in company["domainProducts"] if p["key"] == "sales")
        assert product["name"] == "Commercial" and product["color"] == "#123456"
    revisions = list(
        await session.scalars(
            select(TenantDomainRevision)
            .where(
                TenantDomainRevision.tenant_id == tenant.tenant_id,
                TenantDomainRevision.key == "sales",
            )
            .order_by(TenantDomainRevision.revision)
        )
    )
    assert [(r.revision, r.name, r.color, r.owner) for r in revisions] == [
        (0, "Sales", old_color, revisions[0].owner),
        (1, "Commercial", "#123456", "Bob"),
    ]
    assert revisions[1].proposal_id == uuid.UUID(proposal["id"])
    domain_events = await events(session, tenant, "domain")
    assert [(e.action, e.payload["created"], e.company_ids) for e in domain_events] == [
        ("changed", False, [])
    ]
    assert domain_events[0].payload["domain"]["name"] == "Commercial"
    appearance_events = await events(session, tenant, "appearance")
    assert [(e.action, e.company_ids, e.payload["changed"]) for e in appearance_events] == [
        ("changed", [], ["colors"])
    ]
    assert appearance_events[0].payload["appearance"]["colors"]["sales"] == "#123456"
    audit = decided.json()["audit"]
    assert audit["what"] == "Edit domain Sales" and audit["companyIds"] == []


async def test_edit_domain_refusals(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    headers = tenant.builder.headers
    missing = await client.patch("/domains/retail", json={"name": "Shops"}, headers=headers)
    assert missing.status_code == 404, missing.text
    assert (await client.patch("/domains/sales", json={}, headers=headers)).status_code == 422
    assert (
        await client.patch("/domains/Sales", json={"name": "S"}, headers=headers)
    ).status_code == 422
    taken = await client.patch("/domains/sales", json={"name": "quality"}, headers=headers)
    assert taken.status_code == 409 and taken.json()["code"] == "duplicate_label"
    same = await client.patch("/domains/sales", json={"name": "Sales"}, headers=headers)
    assert same.status_code == 422, same.text
    markup = await client.patch("/domains/sales", json={"name": "Sa<les"}, headers=headers)
    assert markup.status_code == 422, markup.text
    assert (
        await client.patch(
            "/domains/sales", json={"name": "Deals"}, headers=tenant.outsider.headers
        )
    ).status_code == 403
    # A company Owner proposes in its company only; a domain edit spans every company.
    assert (
        await client.patch("/domains/sales", json={"name": "Deals"}, headers=tenant.owner.headers)
    ).status_code == 403


async def test_edit_domain_is_approved_by_an_owner_of_that_domain(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    sales_owner = await persona_with_role(
        session, tenant, RoleName.OWNER, ScopeKind.DOMAIN, domain_keys=("sales",)
    )
    quality_owner = await persona_with_role(
        session, tenant, RoleName.OWNER, ScopeKind.DOMAIN, domain_keys=("quality",)
    )
    proposed = await client.patch(
        "/domains/sales", json={"owner": "Sales team"}, headers=sales_owner.headers
    )
    assert proposed.status_code == 202, proposed.text
    proposal_id = proposed.json()["id"]

    assert (await approve(client, quality_owner, proposal_id)).status_code == 403
    assert (await approve(client, tenant.owner, proposal_id)).status_code == 403
    decided = await approve(client, sales_owner, proposal_id)

    assert decided.status_code == 200, decided.text
    domains = (await client.get("/domains", headers=sales_owner.headers)).json()
    sales = next(d for d in domains if d["key"] == "sales")
    assert sales["owner"] == "Sales team" and sales["revision"] == 1
    appearance = (await client.get("/scene", headers=tenant.governor.headers)).json()["appearance"]
    assert appearance["colors"]["sales"] == sales["defaultColor"]


async def test_custom_domain_reaches_the_proposal_paths_and_the_model_answers(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    domain = await created_domain(client, tenant, "Customer care", "#445566")
    spec = await client.post(
        "/concepts",
        json={
            "type": "spec",
            "companyId": str(tenant.company_id),
            "parentId": str(tenant.root_id),
            "label": "Premium client",
            "domainKey": domain["key"],
        },
        headers=tenant.builder.headers,
    )
    assert spec.status_code == 202, spec.text
    assert spec.json()["heading"] == "Specialisation · Customer care"
    unknown = await propose_concept(
        client, tenant, tenant.builder, "Lost", tenant.root_id, domain_key="retail"
    )
    assert unknown.status_code == 422, unknown.text
    shape = await propose_concept(
        client, tenant, tenant.builder, "Lost", tenant.root_id, domain_key="Retail"
    )
    assert shape.status_code == 422, shape.text

    answer = TeachExtractionAnswer.model_validate(
        {
            "intents": [
                {
                    "kind": "rel",
                    "subject": {"candidate": "c0"},
                    "object": {"newLabel": "Help desk"},
                    "action": "has",
                    "domainKey": domain["key"],
                    "confidence": 0.9,
                    "source": {"start": 0, "end": 10},
                }
            ],
            "unresolved": [],
        }
    )
    assert answer.intents[0].domain_key == "customer_care"
    with pytest.raises(ValueError):
        TeachExtractionAnswer.model_validate(
            {
                "intents": [
                    {
                        "kind": "rel",
                        "subject": {"candidate": "c0"},
                        "object": {"newLabel": "Help desk"},
                        "action": "has",
                        "domainKey": "Customer-care",
                        "confidence": 0.9,
                        "source": {"start": 0, "end": 10},
                    }
                ],
                "unresolved": [],
            }
        )
