"""Decision responses never carry another company's rows; events that carry them list it."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.outbox import Outbox
from app.models.storage.tenant_settings import TenantSettings
from tests.conftest import TenantFixture
from tests.test_proposals import add_company, approved

pytestmark = pytest.mark.asyncio(loop_scope="session")

HIDDEN = "HiddenForeignLabel"


async def _home_concept_with_equivalence(
    client: httpx.AsyncClient, tenant: TenantFixture, label: str
) -> dict:
    """An approved home concept with an approved equivalence to another company's concept."""
    other = await add_company(client, tenant, "Secret")
    home = await approved(client, tenant, label, domain_key="sales")
    created = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": other["company"]["id"],
            "parentId": other["root"]["id"],
            "label": f"{HIDDEN} {label}",
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
    foreign = decided.json()["artefacts"]["concepts"][0]
    equivalence = await client.post(
        "/equivalences",
        json={"aId": home["id"], "bId": foreign["id"]},
        headers=tenant.builder.headers,
    )
    assert equivalence.status_code == 202, equivalence.text
    assert (
        await client.post(
            f"/proposals/{equivalence.json()['id']}/approve", headers=tenant.governor.headers
        )
    ).status_code == 200
    return home


async def _delete_proposal(client: httpx.AsyncClient, tenant: TenantFixture, label: str) -> str:
    home = await _home_concept_with_equivalence(client, tenant, label)
    delete = await client.delete(f"/concepts/{home['id']}", headers=tenant.owner.headers)
    assert delete.status_code == 202, delete.text
    return delete.json()["id"]


async def _assert_events_not_scoped_to_home(session: AsyncSession, tenant: TenantFixture) -> None:
    rows = (await session.scalars(select(Outbox).where(Outbox.tenant_id == tenant.tenant_id))).all()
    leaking = [
        r for r in rows if HIDDEN in str(r.payload) and set(r.company_ids) <= {tenant.company_id}
    ]
    assert leaking == [], [f"{r.aggregate}.{r.action}" for r in leaking]


async def test_approve_response_omits_other_company_rows(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    proposal_id = await _delete_proposal(client, tenant, "Payer")

    decided = await client.post(f"/proposals/{proposal_id}/approve", headers=tenant.owner.headers)

    assert decided.status_code == 200, decided.text
    assert HIDDEN not in decided.text
    assert decided.json()["artefacts"]["concepts"][0]["label"] == "Payer"
    await _assert_events_not_scoped_to_home(session, tenant)


async def test_second_approve_response_omits_other_company_rows(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    settings = await session.get(TenantSettings, tenant.tenant_id)
    assert settings is not None
    settings.two_approvers = True
    await session.commit()
    try:
        proposal_id = await _delete_proposal(client, tenant, "Invoicee")
        first = await client.post(
            f"/proposals/{proposal_id}/approve", headers=tenant.governor.headers
        )
        assert first.status_code == 200, first.text

        second = await client.post(
            f"/proposals/{proposal_id}/second-approve", headers=tenant.owner.headers
        )

        assert second.status_code == 200, second.text
        assert HIDDEN not in second.text
    finally:
        settings.two_approvers = False
        await session.commit()
    await _assert_events_not_scoped_to_home(session, tenant)


async def test_reject_response_omits_other_company_rows(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    other = await add_company(client, tenant, "Secret")
    foreign_created = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": other["company"]["id"],
            "parentId": other["root"]["id"],
            "label": HIDDEN,
            "domainKey": "sales",
            "action": "has",
        },
        headers=tenant.builder.headers,
    )
    foreign = (
        await client.post(
            f"/proposals/{foreign_created.json()['id']}/approve",
            headers=tenant.governor.headers,
        )
    ).json()["artefacts"]["concepts"][0]
    pending = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": str(tenant.company_id),
            "parentId": str(tenant.root_id),
            "label": "Prospect",
            "domainKey": "sales",
            "action": "has",
        },
        headers=tenant.builder.headers,
    )
    assert pending.status_code == 202, pending.text
    link = await client.post(
        "/equivalences",
        json={"aId": pending.json()["conceptId"], "bId": foreign["id"]},
        headers=tenant.builder.headers,
    )
    assert link.status_code == 202, link.text

    rejected = await client.post(
        f"/proposals/{pending.json()['id']}/reject", headers=tenant.owner.headers
    )

    assert rejected.status_code == 200, rejected.text
    assert HIDDEN not in rejected.text
    assert rejected.json()["cascaded"] == []
    await _assert_events_not_scoped_to_home(session, tenant)


@pytest.mark.parametrize("bulk", ["approve-all", "reject-all"])
async def test_bulk_response_and_events_omit_other_company_rows(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession, bulk: str
) -> None:
    await _delete_proposal(client, tenant, f"Debtor {uuid.uuid4().hex[:4]}")

    response = await client.post(f"/proposals/{bulk}", headers=tenant.owner.headers)

    assert response.status_code == 200, response.text
    assert HIDDEN not in response.text
    await _assert_events_not_scoped_to_home(session, tenant)
