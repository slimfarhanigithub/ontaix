"""Cross-company relations are tenant-level proposals: a company-scoped role never decides them."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import TenantFixture
from tests.test_proposals import add_company, approved

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _foreign_concept(client: httpx.AsyncClient, tenant: TenantFixture, other: dict) -> dict:
    created = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": other["company"]["id"],
            "parentId": other["root"]["id"],
            "label": "Client",
            "domainKey": "sales",
            "action": "has",
        },
        headers=tenant.builder.headers,
    )
    assert created.status_code == 202, created.text
    decided = await client.post(
        f"/proposals/{created.json()['id']}/approve", headers=tenant.governor.headers
    )
    assert decided.status_code == 200, decided.text
    return decided.json()["artefacts"]["concepts"][0]


async def _equivalence(client: httpx.AsyncClient, tenant: TenantFixture) -> dict:
    other = await add_company(client, tenant, "Other")
    home = await approved(client, tenant, "Customer", domain_key="sales")
    foreign = await _foreign_concept(client, tenant, other)
    created = await client.post(
        "/equivalences",
        json={"aId": home["id"], "bId": foreign["id"]},
        headers=tenant.builder.headers,
    )
    assert created.status_code == 202, created.text
    return {"proposal": created.json(), "home": home, "foreign": foreign}


async def test_cross_company_proposal_has_tenant_scope(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    proposal = (await _equivalence(client, tenant))["proposal"]

    assert proposal["companyId"] is None
    assert proposal["domainProductId"] is None


async def test_company_owner_cannot_approve_or_reject_a_cross_company_proposal(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    proposal = (await _equivalence(client, tenant))["proposal"]

    approve = await client.post(
        f"/proposals/{proposal['id']}/approve", headers=tenant.owner.headers
    )
    reject = await client.post(f"/proposals/{proposal['id']}/reject", headers=tenant.owner.headers)

    assert approve.status_code == 403, approve.text
    assert reject.status_code == 403, reject.text
    governor = await client.post(
        f"/proposals/{proposal['id']}/approve", headers=tenant.governor.headers
    )
    assert governor.status_code == 200, governor.text


@pytest.mark.parametrize("bulk", ["approve-all", "reject-all"])
async def test_company_owner_bulk_skips_a_cross_company_proposal(
    client: httpx.AsyncClient, tenant: TenantFixture, bulk: str
) -> None:
    proposal = (await _equivalence(client, tenant))["proposal"]

    response = await client.post(f"/proposals/{bulk}", headers=tenant.owner.headers)

    assert response.status_code == 200, response.text
    assert response.json()["remaining"] >= 1
    state = (
        await client.get(f"/proposals/{proposal['id']}", headers=tenant.governor.headers)
    ).json()["state"]
    assert state == "pending"


async def test_company_owner_cannot_propose_into_another_company(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    other = await add_company(client, tenant, "Elsewhere")
    home = await approved(client, tenant, "Buyer", domain_key="sales")
    foreign = await _foreign_concept(client, tenant, other)

    relation = await client.post(
        "/relations",
        json={"type": "relation", "aId": home["id"], "bId": foreign["id"], "action": "buys from"},
        headers=tenant.owner.headers,
    )
    equivalence = await client.post(
        "/equivalences",
        json={"aId": home["id"], "bId": foreign["id"]},
        headers=tenant.owner.headers,
    )

    assert relation.status_code == 403, relation.text
    assert equivalence.status_code == 403, equivalence.text


async def test_change_to_a_cross_company_relation_has_tenant_scope(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    created = await _equivalence(client, tenant)
    relation_id = created["proposal"]["relationId"]
    assert (
        await client.post(
            f"/proposals/{created['proposal']['id']}/approve", headers=tenant.governor.headers
        )
    ).status_code == 200

    by_owner = await client.delete(f"/relations/{relation_id}", headers=tenant.owner.headers)
    removal = await client.delete(f"/relations/{relation_id}", headers=tenant.builder.headers)

    # The owner reads only the home company, so the relation to the other company is not found.
    assert by_owner.status_code == 404, by_owner.text
    assert removal.status_code == 202, removal.text
    assert removal.json()["companyId"] is None
    owner_approve = await client.post(
        f"/proposals/{removal.json()['id']}/approve", headers=tenant.owner.headers
    )
    assert owner_approve.status_code == 403, owner_approve.text
