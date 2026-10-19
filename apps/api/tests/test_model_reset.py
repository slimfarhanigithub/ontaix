"""`reset_model`: one tenant-level change that empties the model and keeps the companies."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import RoleName, ScopeKind
from tests.auth_helpers import signed_in
from tests.conftest import AccountFixture, Browser, TenantFixture, make_tenant
from tests.scoped_users import scoped_user
from tests.test_organization_access import entered
from tests.test_proposals import add_company, approved, propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")

RESET = {"type": "change", "changeKind": "reset_model", "payload": {}}


async def _reset(client: httpx.AsyncClient, headers: dict[str, str]) -> httpx.Response:
    return await client.post("/proposals", json=RESET, headers=headers)


async def test_only_a_tenant_administrator_proposes_a_reset(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    """Owners, Builders and Governors refuse, also a tenant-wide Owner; an Administrator is
    always tenant-wide."""
    await approved(client, tenant, "Pump")
    tenant_owner = await scoped_user(session, tenant, RoleName.OWNER, ScopeKind.TENANT)

    for headers in (
        tenant.builder.headers,
        tenant.owner.headers,
        tenant.governor.headers,
        tenant_owner,
    ):
        refused = await _reset(client, headers)
        assert refused.status_code == 403, refused.text
        assert "tenant administrator or a super admin" in refused.json()["detail"]
    created = await _reset(client, tenant.admin.headers)

    assert created.status_code == 202, created.text
    proposal = created.json()
    assert proposal["changeKind"] == "reset_model"
    assert proposal["title"] == "Reset the model"
    assert proposal["companyId"] is None
    assert "1 concept" in proposal["html"]


async def test_approval_empties_the_model_and_keeps_the_companies(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    other = await add_company(client, tenant, "Apart")
    pump = await approved(client, tenant, "Pump")
    valve = await approved(client, tenant, "Valve", domain_key="quality")
    relation = await client.post(
        "/relations",
        json={"type": "relation", "aId": pump["id"], "bId": valve["id"], "action": "feeds"},
        headers=tenant.builder.headers,
    )
    assert relation.status_code == 202, relation.text
    await client.post(
        f"/proposals/{relation.json()['id']}/approve", headers=tenant.governor.headers
    )
    pending = await propose_concept(client, tenant, tenant.builder, "Seal", tenant.root_id)
    assert pending.status_code == 202, pending.text
    reset = (await _reset(client, tenant.admin.headers)).json()

    bulk = await client.post("/proposals/approve-all", headers=tenant.governor.headers)
    assert bulk.status_code == 200, bulk.text
    still = await client.get(f"/proposals/{reset['id']}", headers=tenant.governor.headers)
    assert still.json()["state"] == "pending"
    seal = await propose_concept(client, tenant, tenant.builder, "Gasket", tenant.root_id)
    assert seal.status_code == 202, seal.text

    decided = await client.post(
        f"/proposals/{reset['id']}/approve", headers=tenant.governor.headers
    )

    assert decided.status_code == 200, decided.text
    assert decided.json()["proposal"]["state"] == "approved"
    assert seal.json()["id"] in {p["id"] for p in decided.json()["cascaded"]}
    scene = (await client.get("/scene", headers=tenant.governor.headers)).json()
    assert {n["kind"] for n in scene["nodes"]} == {"root"}
    assert [link for link in scene["links"] if link.get("kind") != "bind"] == []
    assert {c["id"] for c in scene["companies"]} == {
        str(tenant.company_id),
        other["company"]["id"],
    }
    open_left = (await client.get("/proposals", headers=tenant.governor.headers)).json()
    assert open_left["total"] == 0
    products = (
        await client.get(
            f"/domain-products?companyId={tenant.company_id}", headers=tenant.governor.headers
        )
    ).json()
    assert {"production", "quality"} <= {p["key"] for p in products}


async def test_an_empty_model_has_nothing_to_reset(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    refused = await _reset(client, tenant.admin.headers)

    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "validation_failed"


async def test_a_super_admin_inside_the_organization_resets_it(
    browsers: Callable[[], Browser], super_admin: AccountFixture, client: httpx.AsyncClient
) -> None:
    tenant = await make_tenant()
    await approved(client, tenant, "Pump")
    admin = await signed_in(browsers(), super_admin)
    await entered(admin, tenant.tenant_id)

    created = await admin.call("POST", "/proposals", json=RESET)
    assert created.status_code == 202, created.text
    decided = await admin.call("POST", f"/proposals/{created.json()['id']}/approve")

    assert decided.status_code == 200, decided.text
    scene = (await admin.call("GET", "/scene")).json()
    assert {n["kind"] for n in scene["nodes"]} == {"root"}
