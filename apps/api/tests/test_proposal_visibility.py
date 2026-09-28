"""One read rule: a caller sees a proposal only when it reads every company the proposal touches."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import RoleName, ScopeKind
from app.repositories import (
    app_user_repository,
    group_member_repository,
    group_role_repository,
    user_group_repository,
)
from tests.conftest import DEV_ISSUER, TenantFixture
from tests.test_proposals import add_company, approved

pytestmark = pytest.mark.asyncio(loop_scope="session")

SECRET_LABEL = "SecretCustomerLabel"


async def _cross_company_proposal(client: httpx.AsyncClient, tenant: TenantFixture) -> str:
    other = await add_company(client, tenant, "Secret")
    home = await approved(client, tenant, "Buyer", domain_key="sales")
    created = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": other["company"]["id"],
            "parentId": other["root"]["id"],
            "label": SECRET_LABEL,
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
    return equivalence.json()["id"]


async def _assert_hidden_from_owner(
    client: httpx.AsyncClient, tenant: TenantFixture, proposal_id: str, state: str
) -> None:
    direct = await client.get(f"/proposals/{proposal_id}", headers=tenant.owner.headers)
    assert direct.status_code == 404, direct.text
    listed = await client.get(f"/proposals?filter[state]={state}", headers=tenant.owner.headers)
    assert listed.status_code == 200, listed.text
    assert proposal_id not in {p["id"] for p in listed.json()["items"]}
    scene = await client.get("/scene", headers=tenant.owner.headers)
    assert scene.status_code == 200, scene.text
    assert proposal_id not in {p["id"] for p in scene.json()["proposals"]}
    assert SECRET_LABEL not in scene.text


async def test_open_cross_company_proposal_is_hidden_from_a_one_company_reader(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    proposal_id = await _cross_company_proposal(client, tenant)

    await _assert_hidden_from_owner(client, tenant, proposal_id, "pending")
    governor = await client.get(f"/proposals/{proposal_id}", headers=tenant.governor.headers)
    assert governor.status_code == 200, governor.text


async def test_rejected_cross_company_proposal_stays_hidden(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    proposal_id = await _cross_company_proposal(client, tenant)
    rejected = await client.post(
        f"/proposals/{proposal_id}/reject", headers=tenant.governor.headers
    )
    assert rejected.status_code == 200, rejected.text

    await _assert_hidden_from_owner(client, tenant, proposal_id, "rejected")


async def test_audit_entries_of_unreadable_proposals_are_hidden(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    proposal_id = await _cross_company_proposal(client, tenant)
    assert (
        await client.post(f"/proposals/{proposal_id}/reject", headers=tenant.governor.headers)
    ).status_code == 200
    subject = f"auditor-{uuid.uuid4().hex[:6]}@{tenant.slug}.test"
    user = await app_user_repository.create(
        session,
        tenant_id=tenant.tenant_id,
        issuer=DEV_ISSUER,
        subject=subject,
        email=subject,
        name="Company Auditor",
        department=None,
        company_id=None,
    )
    group = await user_group_repository.create(session, tenant.tenant_id, "home auditors", "")
    await group_member_repository.add(session, tenant.tenant_id, group.id, user.id)
    await group_role_repository.create(
        session,
        tenant_id=tenant.tenant_id,
        group_id=group.id,
        role=RoleName.AUDITOR,
        scope_kind=ScopeKind.COMPANY,
        scope_company_id=tenant.company_id,
        scope_domain_key=None,
    )
    await session.commit()

    audit = await client.get("/audit?pageSize=200", headers={"X-Ontaix-User": subject})

    assert audit.status_code == 200, audit.text
    assert proposal_id not in {e["proposalId"] for e in audit.json()["items"]}
    assert SECRET_LABEL not in audit.text
    assert any(e["what"] == "Buyer" for e in audit.json()["items"])
