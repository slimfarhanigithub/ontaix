"""Moving a concept to another domain: the proposal, its refusals, the rights it needs and what
its approval changes."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import RoleName, ScopeKind
from app.models.storage.outbox import Outbox
from tests.conftest import Persona, TenantFixture
from tests.role_grants import persona_with_role
from tests.test_domains import created_domain
from tests.test_proposals import add_company, approved, propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def move(
    client: httpx.AsyncClient, persona: Persona, concept_id: str, domain_key: str
) -> httpx.Response:
    return await client.post(
        f"/concepts/{concept_id}/move", json={"domainKey": domain_key}, headers=persona.headers
    )


async def approve(client: httpx.AsyncClient, persona: Persona, proposal_id: str) -> httpx.Response:
    return await client.post(f"/proposals/{proposal_id}/approve", headers=persona.headers)


async def products_of(client: httpx.AsyncClient, tenant: TenantFixture) -> dict[str, dict]:
    company = await client.get(f"/companies/{tenant.company_id}", headers=tenant.builder.headers)
    assert company.status_code == 200, company.text
    return {p["key"]: p for p in company.json()["domainProducts"]}


async def test_move_proposal_and_approval(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    plant = await approved(client, tenant, "Plant", domain_key="production")
    line = await approved(client, tenant, "Line", domain_key="production")
    child = await propose_concept(
        client, tenant, tenant.builder, "Press", uuid.UUID(plant["id"]), domain_key="production"
    )
    assert (await approve(client, tenant.governor, child.json()["id"])).status_code == 200
    relation = await client.post(
        "/relations",
        json={"aId": plant["id"], "bId": line["id"], "action": "feeds"},
        headers=tenant.builder.headers,
    )
    assert relation.status_code == 202, relation.text
    assert (await approve(client, tenant.governor, relation.json()["id"])).status_code == 200
    before = await products_of(client, tenant)
    plant_before = (
        await client.get(f"/concepts/{plant['id']}", headers=tenant.builder.headers)
    ).json()
    sales_color = next(
        d["color"]
        for d in (await client.get("/domains", headers=tenant.builder.headers)).json()
        if d["key"] == "sales"
    )

    proposed = await move(client, tenant.builder, plant["id"], "sales")

    assert proposed.status_code == 202, proposed.text
    proposal = proposed.json()
    assert proposal["type"] == "change" and proposal["changeKind"] == "move_concept_domain"
    assert proposal["companyId"] == str(tenant.company_id)
    assert proposal["domainProductId"] == before["production"]["id"]
    assert proposal["title"] == "Move Plant to Sales"
    assert proposal["heading"] == "Change · Production"
    assert proposal["color"] == sales_color
    assert proposal["why"] == "children, relations and bindings stay as they are"

    decided = await approve(client, tenant.governor, proposal["id"])

    assert decided.status_code == 200, decided.text
    result = decided.json()
    moved = result["artefacts"]["concepts"][0]
    assert moved["id"] == plant["id"]
    assert moved["domainKey"] == "sales"
    assert moved["domainProductId"] == before["sales"]["id"]
    assert moved["color"] == sales_color
    assert (moved["x"], moved["y"]) != (plant["x"], plant["y"])
    assert moved["parentId"] == plant["parentId"]
    assert moved["relationCount"] == plant_before["relationCount"] == 3
    assert {p["key"] for p in result["artefacts"]["domainProducts"]} == {"production", "sales"}
    after = await products_of(client, tenant)
    assert after["production"]["revision"] == before["production"]["revision"] + 1
    assert after["sales"]["revision"] == before["sales"]["revision"] + 1
    assert after["production"]["counts"]["members"] == before["production"]["counts"]["members"] - 1
    assert after["sales"]["counts"]["members"] == 1
    press = (
        await client.get(f"/concepts/{child.json()['conceptId']}", headers=tenant.builder.headers)
    ).json()
    assert press["domainKey"] == "production" and press["parentId"] == plant["id"]
    rows = list(
        await session.scalars(
            select(Outbox)
            .where(Outbox.tenant_id == tenant.tenant_id, Outbox.aggregate == "concept")
            .order_by(Outbox.id)
        )
    )
    changed = [r for r in rows if r.action == "changed"]
    assert changed[-1].payload["concept"]["id"] == plant["id"]
    assert "domainKey" in changed[-1].payload["fields"]
    assert changed[-1].payload["proposalId"] == proposal["id"]
    assert changed[-1].company_ids == [tenant.company_id]
    bumps = [
        r.payload["domainProduct"]["key"]
        for r in await session.scalars(
            select(Outbox).where(
                Outbox.tenant_id == tenant.tenant_id,
                Outbox.aggregate == "domain_product",
                Outbox.action == "changed",
            )
        )
        if r.payload["fields"] == ["revision"]
    ]
    assert bumps.count("sales") >= 1 and bumps.count("production") >= 1


async def test_move_refusals(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    plant = await approved(client, tenant, "Plant", domain_key="production")
    pending = (
        await propose_concept(client, tenant, tenant.builder, "Draft", tenant.root_id)
    ).json()

    root = await move(client, tenant.builder, str(tenant.root_id), "sales")
    assert root.status_code == 409 and root.json()["code"] == "root_concept"
    waiting = await move(client, tenant.builder, pending["conceptId"], "sales")
    assert waiting.status_code == 409 and waiting.json()["code"] == "concept_pending"
    same = await move(client, tenant.builder, plant["id"], "production")
    assert same.status_code == 422, same.text
    unknown = await move(client, tenant.builder, plant["id"], "retail")
    assert unknown.status_code == 422, unknown.text
    shape = await move(client, tenant.builder, plant["id"], "Sales")
    assert shape.status_code == 422, shape.text
    missing = await move(client, tenant.builder, str(uuid.uuid4()), "sales")
    assert missing.status_code == 404, missing.text
    assert (await move(client, tenant.outsider, plant["id"], "sales")).status_code == 403


async def test_move_needs_rights_in_both_domains(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    plant = await approved(client, tenant, "Plant", domain_key="production")
    production_builder = await persona_with_role(
        session, tenant, RoleName.BUILDER, ScopeKind.DOMAIN, domain_keys=("production",)
    )
    both_builder = await persona_with_role(
        session, tenant, RoleName.BUILDER, ScopeKind.DOMAIN, domain_keys=("production", "sales")
    )
    production_owner = await persona_with_role(
        session, tenant, RoleName.OWNER, ScopeKind.DOMAIN, domain_keys=("production",)
    )
    both_owner = await persona_with_role(
        session, tenant, RoleName.OWNER, ScopeKind.DOMAIN, domain_keys=("production", "sales")
    )

    assert (await move(client, production_builder, plant["id"], "sales")).status_code == 403
    proposed = await move(client, both_builder, plant["id"], "sales")
    assert proposed.status_code == 202, proposed.text
    proposal_id = proposed.json()["id"]
    assert (await approve(client, production_owner, proposal_id)).status_code == 403
    decided = await approve(client, both_owner, proposal_id)
    assert decided.status_code == 200, decided.text
    assert decided.json()["artefacts"]["concepts"][0]["domainKey"] == "sales"

    # The company Owner covers every domain of its company.
    line = await approved(client, tenant, "Line", domain_key="production")
    proposed = await move(client, tenant.owner, line["id"], "quality")
    assert proposed.status_code == 202, proposed.text
    assert (await approve(client, tenant.owner, proposed.json()["id"])).status_code == 200


async def test_move_into_a_custom_domain_creates_the_product_and_stays_in_the_company(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    other = (await add_company(client, tenant, "Second"))["company"]
    domain = await created_domain(client, tenant, "Customer care", "#445566")
    plant = await approved(client, tenant, "Plant", domain_key="production")
    assert "customer_care" not in await products_of(client, tenant)

    proposed = await move(client, tenant.builder, plant["id"], domain["key"])
    assert proposed.status_code == 202, proposed.text
    decided = await approve(client, tenant.governor, proposed.json()["id"])

    assert decided.status_code == 200, decided.text
    moved = decided.json()["artefacts"]["concepts"][0]
    assert moved["domainKey"] == "customer_care" and moved["color"] == "#445566"
    assert moved["companyId"] == str(tenant.company_id)
    products = await products_of(client, tenant)
    assert products["customer_care"]["revision"] == 1
    assert products["customer_care"]["counts"]["members"] == 1
    assert moved["domainProductId"] == products["customer_care"]["id"]
    other_products = (
        await client.get(f"/companies/{other['id']}", headers=tenant.builder.headers)
    ).json()["domainProducts"]
    assert all(p["counts"]["members"] == 0 for p in other_products)
