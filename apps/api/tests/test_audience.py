"""Every outbox row and audit entry lists the companies it names, and readers are held to them."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import db_client
from app.models.api.actor import Actor
from app.models.storage.audit_entry import AuditEntry
from app.models.storage.base import ActorKind, RoleName, ScopeKind
from app.models.storage.outbox import Outbox
from app.models.storage.proposal import Proposal
from app.repositories import (
    app_user_repository,
    audit_repository,
    group_member_repository,
    group_role_repository,
    proposal_repository,
    tenant_repository,
    user_group_repository,
)
from app.services import company_service, outbox_service
from app.services.ontology_view_service import load_view
from tests.conftest import DEV_ISSUER, TenantFixture
from tests.test_proposals import add_company, approved, propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")

SECRET_LABEL = "AudienceSecretLabel"
SHORT_LOCK_TIMEOUT_MS = 200
SYSTEM = Actor(kind="system", id=None, name=None)


async def _foreign_tenant_company(session: AsyncSession) -> uuid.UUID:
    slug = f"f-{uuid.uuid4().hex[:10]}"
    foreign = await tenant_repository.create(session, slug, f"Tenant {slug}")
    view = await load_view(session, foreign.id)
    company = await company_service.add_company(session, view, "Foreign", "", is_home=True)
    await session.commit()
    return company.id


async def _equivalence(client: httpx.AsyncClient, tenant: TenantFixture) -> dict:
    """An approved home concept, an approved concept of a second company, and a pending
    equivalence between them."""
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
    return {
        "proposalId": equivalence.json()["id"],
        "otherId": other["company"]["id"],
        "otherAdded": f"{other['company']['name']} added",
    }


async def _company_auditor(session: AsyncSession, tenant: TenantFixture) -> dict[str, str]:
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
    return {"X-Ontaix-User": subject}


async def test_outbox_refuses_a_company_of_another_tenant(
    tenant: TenantFixture, session: AsyncSession
) -> None:
    foreign_company = await _foreign_tenant_company(session)

    with pytest.raises(DBAPIError, match="outside tenant"):
        await outbox_service.emit(
            session,
            tenant.tenant_id,
            SYSTEM,
            "company.created",
            {},
            company_ids=[tenant.company_id, foreign_company],
        )
    await session.rollback()


async def test_audit_refuses_a_company_of_another_tenant(
    tenant: TenantFixture, session: AsyncSession
) -> None:
    foreign_company = await _foreign_tenant_company(session)

    with pytest.raises(DBAPIError, match="outside tenant"):
        await audit_repository.create(
            session,
            tenant_id=tenant.tenant_id,
            actor_kind=ActorKind.SYSTEM,
            actor_user_id=None,
            kind="company",
            what="Foreign added",
            ok=True,
            proposal_id=None,
            company_ids=[foreign_company],
        )
    await session.rollback()


async def test_cross_company_events_and_audit_list_both_companies(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    created = await _equivalence(client, tenant)
    decided = await client.post(
        f"/proposals/{created['proposalId']}/approve", headers=tenant.governor.headers
    )
    assert decided.status_code == 200, decided.text
    both = {tenant.company_id, uuid.UUID(created["otherId"])}

    rows = (await session.scalars(select(Outbox).where(Outbox.tenant_id == tenant.tenant_id))).all()
    about_it = [
        r
        for r in rows
        if created["proposalId"] in str(r.payload) and r.aggregate in {"proposal", "relation"}
    ]
    assert {f"{r.aggregate}.{r.action}" for r in about_it} >= {
        "proposal.created",
        "relation.created",
        "proposal.approved",
    }
    assert all(set(r.company_ids) == both for r in about_it)
    entry = await session.scalar(
        select(AuditEntry).where(AuditEntry.proposal_id == uuid.UUID(created["proposalId"]))
    )
    assert entry is not None and set(entry.company_ids) == both
    appended = [r for r in rows if r.aggregate == "audit" and r.payload.get("id") == entry.id]
    assert len(appended) == 1 and set(appended[0].company_ids) == both
    added = await session.scalar(
        select(AuditEntry).where(
            AuditEntry.tenant_id == tenant.tenant_id, AuditEntry.what == created["otherAdded"]
        )
    )
    assert added is not None and added.company_ids == [uuid.UUID(created["otherId"])]


async def test_one_company_auditor_reads_only_its_company_entries(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    created = await _equivalence(client, tenant)
    assert (
        await client.post(
            f"/proposals/{created['proposalId']}/approve", headers=tenant.governor.headers
        )
    ).status_code == 200
    auditor = await _company_auditor(session, tenant)

    audit = await client.get("/audit?pageSize=200", headers=auditor)
    everything = await client.get("/audit?pageSize=200", headers=tenant.governor.headers)

    assert audit.status_code == 200, audit.text
    body = audit.json()
    whats = {e["what"] for e in body["items"]}
    assert "Buyer" in whats
    assert created["otherAdded"] not in whats
    assert SECRET_LABEL not in audit.text
    assert all(e["companyIds"] == [str(tenant.company_id)] for e in body["items"])
    assert body["total"] == len(body["items"])
    assert everything.json()["total"] > body["total"]
    assert created["otherAdded"] in {e["what"] for e in everything.json()["items"]}


async def test_row_lock_timeout_answers_503_busy(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    waiting = (
        await propose_concept(client, tenant, tenant.builder, "RowLocked", tenant.root_id)
    ).json()
    monkeypatch.setattr(proposal_repository, "DECISION_LOCK_TIMEOUT_MS", SHORT_LOCK_TIMEOUT_MS)
    holder = db_client.get_session_factory()()
    try:
        await holder.execute(
            select(Proposal).where(Proposal.id == uuid.UUID(waiting["id"])).with_for_update()
        )
        response = await client.post(
            f"/proposals/{waiting['id']}/approve", headers=tenant.governor.headers
        )
    finally:
        await holder.rollback()
        await holder.close()

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "busy"
    assert int(response.headers["Retry-After"]) > 0
    retried = await client.post(
        f"/proposals/{waiting['id']}/approve", headers=tenant.governor.headers
    )
    assert retried.status_code == 200, retried.text


async def test_company_removal_events_and_audit_name_the_removed_company(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    other = await add_company(client, tenant, "Leaving")
    other_id = uuid.UUID(other["company"]["id"])
    proposed = await client.delete(f"/companies/{other_id}", headers=tenant.builder.headers)
    assert proposed.status_code == 202, proposed.text

    decided = await client.post(
        f"/proposals/{proposed.json()['id']}/approve", headers=tenant.governor.headers
    )

    assert decided.status_code == 200, decided.text
    gone = await client.get(f"/companies/{other_id}", headers=tenant.governor.headers)
    assert gone.status_code == 404, gone.text
    removed = await session.scalar(
        select(Outbox).where(
            Outbox.tenant_id == tenant.tenant_id,
            Outbox.aggregate == "company",
            Outbox.action == "removed",
        )
    )
    assert removed is not None and removed.company_ids == [other_id]
    entry = await session.scalar(
        select(AuditEntry).where(AuditEntry.proposal_id == uuid.UUID(proposed.json()["id"]))
    )
    assert entry is not None and entry.company_ids == [other_id]
