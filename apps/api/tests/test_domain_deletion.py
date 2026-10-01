"""`DELETE /domain-products/{id}`: one company's domain emptied through a `delete_domain` change."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import RoleName, ScopeKind
from app.models.storage.concept import Concept
from app.models.storage.relation import Relation
from tests.conftest import TenantFixture
from tests.scoped_users import scoped_user
from tests.test_deletion_impact import _approved_child, _approved_relation
from tests.test_proposals import add_company, approved, propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _quality_domain(client: httpx.AsyncClient, tenant: TenantFixture) -> dict:
    """Quality holds Audit (with the production child Sample) and Gauge, related to the
    production concept Press; a pending Checklist waits in quality."""
    home = str(tenant.company_id)
    audit = await approved(client, tenant, "Audit", domain_key="quality")
    sample = await _approved_child(client, tenant, home, audit["id"], "Sample", "production")
    gauge = await approved(client, tenant, "Gauge", domain_key="quality")
    press = await approved(client, tenant, "Press")
    await _approved_relation(
        client,
        tenant,
        "/relations",
        {"type": "relation", "aId": gauge["id"], "bId": press["id"], "action": "measures"},
    )
    checklist = await propose_concept(
        client, tenant, tenant.builder, "Checklist", tenant.root_id, domain_key="quality"
    )
    assert checklist.status_code == 202, checklist.text
    products = (
        await client.get(f"/domain-products?companyId={home}", headers=tenant.governor.headers)
    ).json()
    quality = next(p for p in products if p["key"] == "quality")
    return {
        "audit": audit,
        "sample": sample,
        "gauge": gauge,
        "press": press,
        "checklist": checklist.json(),
        "quality": quality,
    }


async def test_delete_domain_proposal_and_approval_by_a_domain_owner(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    domain = await _quality_domain(client, tenant)
    product_id = domain["quality"]["id"]

    response = await client.delete(f"/domain-products/{product_id}", headers=tenant.builder.headers)

    assert response.status_code == 202, response.text
    proposal = response.json()
    assert proposal["changeKind"] == "delete_domain"
    assert proposal["title"] == "Delete Quality"
    assert proposal["domainProductId"] == product_id
    assert proposal["html"] == (
        "Delete <b>Quality</b> with its 3 concepts, 1 descendant, 5 relations and 1 open proposal"
    )
    assert (
        proposal["why"]
        == "Audit, Gauge, Checklist and Sample go with it · the domain stays available"
    )
    assert await session.get(Concept, uuid.UUID(domain["audit"]["id"])) is not None

    quality_owner = await scoped_user(
        session, tenant, RoleName.OWNER, ScopeKind.DOMAIN, domain_key="quality"
    )
    decided = await client.post(f"/proposals/{proposal['id']}/approve", headers=quality_owner)

    assert decided.status_code == 200, decided.text
    result = decided.json()
    assert {c["label"] for c in result["artefacts"]["concepts"]} == {"Audit", "Gauge", "Sample"}
    assert [p["id"] for p in result["cascaded"]] == [domain["checklist"]["id"]]
    product = next(p for p in result["artefacts"]["domainProducts"] if p["id"] == product_id)
    assert product["revision"] == domain["quality"]["revision"] + 1
    session.expire_all()
    for key in ("audit", "sample", "gauge"):
        assert await session.get(Concept, uuid.UUID(domain[key]["id"])) is None
    assert await session.get(Concept, uuid.UUID(domain["checklist"]["conceptId"])) is None
    assert await session.get(Concept, uuid.UUID(domain["press"]["id"])) is not None
    assert await session.get(Relation, uuid.UUID(domain["checklist"]["relationId"])) is None
    still = await client.get(f"/domain-products/{product_id}", headers=tenant.governor.headers)
    assert still.status_code == 200, still.text
    assert still.json()["counts"]["members"] == 0
    domains = await client.get("/domains", headers=tenant.governor.headers)
    assert domains.status_code == 200, domains.text
    assert "quality" in {d["key"] for d in domains.json()}


async def test_delete_domain_approval_by_the_company_owner(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    domain = await _quality_domain(client, tenant)
    proposed = await client.delete(
        f"/domain-products/{domain['quality']['id']}", headers=tenant.owner.headers
    )
    assert proposed.status_code == 202, proposed.text
    other_domain_owner = await scoped_user(
        session, tenant, RoleName.OWNER, ScopeKind.DOMAIN, domain_key="sales"
    )

    refused = await client.post(
        f"/proposals/{proposed.json()['id']}/approve", headers=other_domain_owner
    )
    assert refused.status_code == 403, refused.text
    decided = await client.post(
        f"/proposals/{proposed.json()['id']}/approve", headers=tenant.owner.headers
    )

    assert decided.status_code == 200, decided.text
    session.expire_all()
    assert await session.get(Concept, uuid.UUID(domain["gauge"]["id"])) is None


async def test_delete_domain_is_scoped_to_readers_and_proposers(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    domain = await _quality_domain(client, tenant)
    product_id = domain["quality"]["id"]
    other = await add_company(client, tenant, "Apart")
    other_owner = await scoped_user(
        session,
        tenant,
        RoleName.OWNER,
        ScopeKind.COMPANY,
        company_id=uuid.UUID(other["company"]["id"]),
    )
    sales_builder = await scoped_user(
        session, tenant, RoleName.BUILDER, ScopeKind.DOMAIN, domain_key="sales"
    )

    assert (
        await client.delete(f"/domain-products/{product_id}", headers=tenant.outsider.headers)
    ).status_code == 404
    assert (
        await client.delete(f"/domain-products/{product_id}", headers=other_owner)
    ).status_code == 404
    assert (
        await client.delete(f"/domain-products/{product_id}", headers=sales_builder)
    ).status_code == 403
    assert (
        await client.delete(f"/domain-products/{uuid.uuid4()}", headers=tenant.builder.headers)
    ).status_code == 404
