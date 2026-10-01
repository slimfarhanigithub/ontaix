"""`POST /proposals/bulk-delete`: one `delete_bulk` change for several concepts and domains."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import RoleName, ScopeKind
from app.models.storage.concept import Concept
from tests.conftest import TenantFixture
from tests.scoped_users import scoped_user
from tests.test_deletion_impact import _approved_child
from tests.test_proposals import add_company, approved, propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _bulk(
    client: httpx.AsyncClient, headers: dict[str, str], **body: object
) -> httpx.Response:
    return await client.post("/proposals/bulk-delete", json=body, headers=headers)


async def _selection(client: httpx.AsyncClient, tenant: TenantFixture) -> dict:
    """Mill (production) with its child Roller and pending Blade under Roller; Quality holds
    Inspector; Depot (logistics) stays."""
    home = str(tenant.company_id)
    mill = await approved(client, tenant, "Mill")
    roller = await _approved_child(client, tenant, home, mill["id"], "Roller", "production")
    blade = await propose_concept(
        client, tenant, tenant.builder, "Blade", uuid.UUID(roller["id"]), domain_key="production"
    )
    assert blade.status_code == 202, blade.text
    inspector = await approved(client, tenant, "Inspector", domain_key="quality")
    depot = await approved(client, tenant, "Depot", domain_key="logistics")
    products = (
        await client.get(f"/domain-products?companyId={home}", headers=tenant.governor.headers)
    ).json()
    return {
        "mill": mill,
        "roller": roller,
        "blade": blade.json(),
        "inspector": inspector,
        "depot": depot,
        "quality": next(p for p in products if p["key"] == "quality"),
        "production": next(p for p in products if p["key"] == "production"),
    }


async def test_bulk_limits_and_shapes(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    home = str(tenant.company_id)
    depot = await approved(client, tenant, "Depot", domain_key="logistics")
    other = await add_company(client, tenant, "Apart")
    far = await _approved_child(
        client, tenant, other["company"]["id"], other["root"]["id"], "Far", "sales"
    )

    too_many_concepts = await _bulk(
        client,
        tenant.builder.headers,
        companyId=home,
        conceptIds=[str(uuid.uuid4()) for _ in range(201)],
    )
    assert too_many_concepts.status_code == 422
    too_many_products = await _bulk(
        client,
        tenant.builder.headers,
        companyId=home,
        domainProductIds=[str(uuid.uuid4()) for _ in range(21)],
    )
    assert too_many_products.status_code == 422
    empty = await _bulk(client, tenant.builder.headers, companyId=home, conceptIds=[])
    assert empty.status_code == 422
    twice = await _bulk(
        client, tenant.builder.headers, companyId=home, conceptIds=[depot["id"], depot["id"]]
    )
    assert twice.status_code == 422
    spanning = await _bulk(
        client, tenant.builder.headers, companyId=home, conceptIds=[depot["id"], far["id"]]
    )
    assert spanning.status_code == 422
    assert spanning.json()["code"] == "validation_failed"
    root = await _bulk(
        client, tenant.builder.headers, companyId=home, conceptIds=[str(tenant.root_id)]
    )
    assert root.status_code == 409
    assert root.json()["code"] == "root_concept"
    unknown = await _bulk(
        client, tenant.builder.headers, companyId=home, conceptIds=[str(uuid.uuid4())]
    )
    assert unknown.status_code == 404
    unknown_product = await _bulk(
        client, tenant.builder.headers, companyId=home, domainProductIds=[str(uuid.uuid4())]
    )
    assert unknown_product.status_code == 404
    outsider = await _bulk(
        client, tenant.outsider.headers, companyId=home, conceptIds=[depot["id"]]
    )
    assert outsider.status_code == 404


async def test_bulk_proposing_needs_rights_in_every_scope(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    selection = await _selection(client, tenant)
    quality_builder = await scoped_user(
        session, tenant, RoleName.BUILDER, ScopeKind.DOMAIN, domain_key="quality"
    )

    refused = await _bulk(
        client,
        quality_builder,
        companyId=str(tenant.company_id),
        conceptIds=[selection["inspector"]["id"], selection["mill"]["id"]],
    )
    assert refused.status_code == 403, refused.text
    allowed = await _bulk(
        client,
        quality_builder,
        companyId=str(tenant.company_id),
        domainProductIds=[selection["quality"]["id"]],
    )
    assert allowed.status_code == 202, allowed.text


async def test_bulk_is_all_or_nothing_and_needs_approval_rights_everywhere(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    selection = await _selection(client, tenant)
    home = str(tenant.company_id)

    response = await _bulk(
        client,
        tenant.builder.headers,
        companyId=home,
        conceptIds=[selection["mill"]["id"]],
        domainProductIds=[selection["quality"]["id"]],
    )

    assert response.status_code == 202, response.text
    proposal = response.json()
    assert proposal["changeKind"] == "delete_bulk"
    assert proposal["title"] == "Delete 1 concept and 1 domain"
    assert proposal["html"] == (
        "Delete <b>Mill</b>, <b>Inspector</b> with their 2 descendants, 4 relations"
        " and 1 open proposal"
    )
    assert proposal["companyId"] == home and proposal["domainProductId"] is None

    quality_owner = await scoped_user(
        session, tenant, RoleName.OWNER, ScopeKind.DOMAIN, domain_key="quality"
    )
    refused = await client.post(f"/proposals/{proposal['id']}/approve", headers=quality_owner)
    assert refused.status_code == 403, refused.text
    session.expire_all()
    for key in ("mill", "roller", "inspector"):
        assert await session.get(Concept, uuid.UUID(selection[key]["id"])) is not None
    still_open = await client.get(f"/proposals/{proposal['id']}", headers=tenant.governor.headers)
    assert still_open.json()["state"] == "pending"

    decided = await client.post(
        f"/proposals/{proposal['id']}/approve", headers=tenant.governor.headers
    )

    assert decided.status_code == 200, decided.text
    result = decided.json()
    assert {c["label"] for c in result["artefacts"]["concepts"]} == {"Mill", "Roller", "Inspector"}
    assert [p["id"] for p in result["cascaded"]] == [selection["blade"]["id"]]
    bumped = {p["key"]: p["revision"] for p in result["artefacts"]["domainProducts"]}
    assert bumped == {
        "production": selection["production"]["revision"] + 1,
        "quality": selection["quality"]["revision"] + 1,
    }
    session.expire_all()
    for key in ("mill", "roller", "inspector"):
        assert await session.get(Concept, uuid.UUID(selection[key]["id"])) is None
    assert await session.get(Concept, uuid.UUID(selection["blade"]["conceptId"])) is None
    assert await session.get(Concept, uuid.UUID(selection["depot"]["id"])) is not None


async def test_bulk_of_one_domain_is_approved_by_its_owner(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    selection = await _selection(client, tenant)
    proposed = await _bulk(
        client,
        tenant.builder.headers,
        companyId=str(tenant.company_id),
        conceptIds=[selection["inspector"]["id"]],
        domainProductIds=[selection["quality"]["id"]],
    )
    assert proposed.status_code == 202, proposed.text
    assert proposed.json()["title"] == "Delete 1 concept and 1 domain"
    quality_owner = await scoped_user(
        session, tenant, RoleName.OWNER, ScopeKind.DOMAIN, domain_key="quality"
    )

    decided = await client.post(
        f"/proposals/{proposed.json()['id']}/approve", headers=quality_owner
    )

    assert decided.status_code == 200, decided.text
    assert [c["label"] for c in decided.json()["artefacts"]["concepts"]] == ["Inspector"]
    assert [p["key"] for p in decided.json()["artefacts"]["domainProducts"]] == ["quality"]
