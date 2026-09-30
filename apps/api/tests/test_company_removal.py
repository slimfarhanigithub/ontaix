"""Removing a company: the proposal names what goes; approval cascades, unlinks and purges."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.attribute import Attribute
from app.models.storage.audit_entry import AuditEntry
from app.models.storage.base import RoleName, ScopeKind
from app.models.storage.company import Company
from app.models.storage.concept import Concept
from app.models.storage.concept_expansion import ConceptExpansion
from app.models.storage.document_extraction_job import DocumentExtractionJob
from app.models.storage.document_import import DocumentImport
from app.models.storage.domain_product import DomainProduct
from app.models.storage.outbox import Outbox
from app.models.storage.relation import Relation
from app.repositories import (
    concept_expansion_repository,
    document_extraction_job_repository,
    document_import_repository,
)
from tests.conftest import TenantFixture
from tests.scoped_users import scoped_user
from tests.test_deletion_impact import _approved_child, _approved_relation
from tests.test_proposals import add_company, approved

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _leaving_company(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> dict:
    """A second company with an approved concept and its child, an equivalence to a home
    concept, a pending concept, a proposed attribute, an expansion, an import and a job."""
    other = await add_company(client, tenant, "Leaving")
    company_id = other["company"]["id"]
    part = await _approved_child(client, tenant, company_id, other["root"]["id"], "Part", "sales")
    piece = await _approved_child(client, tenant, company_id, part["id"], "Piece", "production")
    home = await approved(client, tenant, "Buyer", domain_key="sales")
    await _approved_relation(
        client, tenant, "/equivalences", {"aId": home["id"], "bId": part["id"]}
    )
    pending = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": company_id,
            "parentId": other["root"]["id"],
            "label": "Draft part",
            "domainKey": "sales",
            "action": "has",
        },
        headers=tenant.builder.headers,
    )
    assert pending.status_code == 202, pending.text
    attribute = await client.post(
        "/proposals",
        json={
            "type": "attr",
            "conceptId": part["id"],
            "name": "weight",
            "attributeType": "number",
            "value": "3",
        },
        headers=tenant.builder.headers,
    )
    assert attribute.status_code == 202, attribute.text
    expansion = await concept_expansion_repository.create(
        session,
        tenant_id=tenant.tenant_id,
        actor_user_id=tenant.builder.user_id,
        company_id=uuid.UUID(company_id),
        concept_id=uuid.UUID(part["id"]),
        session_id=None,
        depth=None,
        max_children=None,
        drafts=[{"label": "x"}],
        notes=[{"text": "x"}],
    )
    document = await document_import_repository.create(
        session,
        tenant_id=tenant.tenant_id,
        actor_user_id=tenant.builder.user_id,
        file_name="notes.txt",
        media_type="text/plain",
        sha256=bytes(32),
        sentence_count=1,
        extracted_chars=10,
    )
    job = await document_extraction_job_repository.create(
        session,
        tenant_id=tenant.tenant_id,
        actor_user_id=tenant.builder.user_id,
        import_id=document.id,
        company_id=uuid.UUID(company_id),
        chunks=1,
        token_ceiling=1000,
        node_ceiling=10,
    )
    await session.commit()
    return {
        "company_id": uuid.UUID(company_id),
        "part": uuid.UUID(part["id"]),
        "piece": uuid.UUID(piece["id"]),
        "home": uuid.UUID(home["id"]),
        "pending_proposal": pending.json()["id"],
        "attribute_proposal": attribute.json()["id"],
        "expansion": expansion.id,
        "import": document.id,
        "job": job.id,
    }


async def test_removal_proposal_names_what_goes(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    leaving = await _leaving_company(client, tenant, session)

    response = await client.delete(
        f"/companies/{leaving['company_id']}", headers=tenant.builder.headers
    )

    assert response.status_code == 202, response.text
    proposal = response.json()
    assert proposal["changeKind"] == "remove_company"
    assert proposal["html"].startswith("Remove <b>Leaving")
    assert "3 concepts" in proposal["html"]
    assert "(1 across companies)" in proposal["html"]
    assert "1 attribute" in proposal["html"]
    assert "2 open proposals" in proposal["html"]
    assert proposal["why"].startswith("Part, Piece and Draft part go with it")
    assert proposal["why"].endswith(
        "cross-company relations and equivalences to it are removed too"
    )


async def test_approval_cascades_unlinks_and_purges_the_company(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    leaving = await _leaving_company(client, tenant, session)
    company_id = leaving["company_id"]
    proposed = await client.delete(f"/companies/{company_id}", headers=tenant.builder.headers)
    assert proposed.status_code == 202, proposed.text
    proposal_id = proposed.json()["id"]
    equivalence = await session.scalar(
        select(Relation).where(Relation.a_id == leaving["home"], Relation.b_id == leaving["part"])
    )
    assert equivalence is not None
    equivalence_id = equivalence.id
    other_owner = await scoped_user(
        session, tenant, RoleName.OWNER, ScopeKind.COMPANY, company_id=company_id
    )

    home_owner = await client.post(
        f"/proposals/{proposal_id}/approve", headers=tenant.owner.headers
    )
    assert home_owner.status_code == 403, home_owner.text
    decided = await client.post(f"/proposals/{proposal_id}/approve", headers=other_owner)

    assert decided.status_code == 200, decided.text
    result = decided.json()
    assert {p["id"] for p in result["cascaded"]} == {
        leaving["pending_proposal"],
        leaving["attribute_proposal"],
    }
    # The equivalence joins the home company too, which this owner does not read.
    assert result["artefacts"]["relations"] == []
    assert result["artefacts"]["companies"][0]["id"] == str(company_id)

    session.expire_all()
    assert (
        await client.get(f"/companies/{company_id}", headers=tenant.governor.headers)
    ).status_code == 404
    assert await session.get(Company, company_id) is None
    for concept_id in (leaving["part"], leaving["piece"]):
        assert await session.get(Concept, concept_id) is None
    assert await session.get(Concept, leaving["home"]) is not None
    assert await session.get(Relation, equivalence_id) is None
    assert (
        await session.scalar(select(DomainProduct).where(DomainProduct.company_id == company_id))
    ) is None
    assert (
        await session.scalar(select(Attribute).where(Attribute.concept_id == leaving["part"]))
    ) is None
    assert await session.get(ConceptExpansion, leaving["expansion"]) is None
    assert await session.get(DocumentExtractionJob, leaving["job"]) is None
    assert await session.get(DocumentImport, leaving["import"]) is None
    removed_events = (
        await session.scalars(
            select(Outbox).where(
                Outbox.tenant_id == tenant.tenant_id,
                Outbox.aggregate == "relation",
                Outbox.action == "removed",
            )
        )
    ).all()
    unlinked = [e for e in removed_events if e.payload.get("relationId") == str(equivalence_id)]
    assert len(unlinked) == 1 and unlinked[0].payload["dying"] is True
    assert set(unlinked[0].company_ids) == {tenant.company_id, company_id}
    entries = (
        await session.scalars(
            select(AuditEntry).where(
                AuditEntry.tenant_id == tenant.tenant_id,
                AuditEntry.company_ids.contains([company_id]),
            )
        )
    ).all()
    kinds = {e.kind for e in entries}
    assert "company" in kinds and "change" in kinds
    assert any(e.proposal_id == uuid.UUID(proposal_id) for e in entries)
    history = await client.get(f"/proposals/{proposal_id}", headers=tenant.governor.headers)
    assert history.status_code == 200, history.text
    assert history.json()["state"] == "approved"
    assert history.json()["companyId"] is None
