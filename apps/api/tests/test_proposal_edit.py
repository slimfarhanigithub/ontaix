"""Editing a pending draft in place: `PATCH /proposals/{id}` and `expectedRevision` on approval."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.audit_entry import AuditEntry
from app.models.storage.base import RoleName, ScopeKind
from app.models.storage.concept import Concept
from app.models.storage.outbox import Outbox
from app.models.storage.relation import Relation
from app.models.storage.tenant_settings import TenantSettings
from tests.conftest import TenantFixture
from tests.scoped_users import scoped_user
from tests.test_proposals import add_company, approved, propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _patch(
    client: httpx.AsyncClient, proposal_id: str, headers: dict[str, str], **fields: object
) -> httpx.Response:
    return await client.patch(f"/proposals/{proposal_id}", json=fields, headers=headers)


async def _pending_relation(
    client: httpx.AsyncClient, tenant: TenantFixture, a_id: str, b_id: str, action: str
) -> dict:
    created = await client.post(
        "/relations",
        json={"type": "relation", "aId": a_id, "bId": b_id, "action": action},
        headers=tenant.builder.headers,
    )
    assert created.status_code == 202, created.text
    return created.json()


async def _events(session: AsyncSession, tenant: TenantFixture, proposal_id: str) -> set[str]:
    rows = (await session.scalars(select(Outbox).where(Outbox.tenant_id == tenant.tenant_id))).all()
    return {f"{r.aggregate}.{r.action}" for r in rows if proposal_id in str(r.payload)}


async def test_edit_concept_label_rebuilds_texts_and_rewrites_dependants(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    motor = await approved(client, tenant, "Motor")
    pump = (await propose_concept(client, tenant, tenant.builder, "Pumpp", tenant.root_id)).json()
    child = (
        await propose_concept(
            client, tenant, tenant.builder, "Impeller", parent_label="Pumpp", domain_key="quality"
        )
    ).json()
    relation = await _pending_relation(client, tenant, pump["conceptId"], motor["id"], "drives")
    assert pump["revision"] == 0
    assert child["deps"] == ["Pumpp"] and child["waitFor"] == "Pumpp"

    response = await _patch(client, pump["id"], tenant.builder.headers, revision=0, label="Pump")

    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["revision"] == 1
    assert edited["title"] == "Pump"
    assert edited["html"] == f"<b>Pump</b> <i>· {tenant.company_name} <b>operates</b> Pump</i>"
    assert edited["artefacts"]["concepts"][0]["label"] == "Pump"
    assert edited["artefacts"]["relations"][0]["label"] == "operates"
    row = await session.get(Concept, uuid.UUID(pump["conceptId"]))
    assert row is not None
    await session.refresh(row)
    assert row.label == "Pump"
    child_now = (
        await client.get(f"/proposals/{child['id']}", headers=tenant.governor.headers)
    ).json()
    assert child_now["deps"] == ["Pump"]
    assert child_now["waitFor"] == "Pump"
    assert child_now["parentLabel"] == "Pump"
    assert child_now["revision"] == 0
    relation_now = (
        await client.get(f"/proposals/{relation['id']}", headers=tenant.governor.headers)
    ).json()
    assert relation_now["waitFor"] == "Pump and Motor"
    events = await _events(session, tenant, pump["id"])
    assert {"proposal.changed", "concept.changed"} <= events
    assert "relation.changed" not in events
    entry = await session.scalar(
        select(AuditEntry).where(
            AuditEntry.proposal_id == uuid.UUID(pump["id"]), AuditEntry.kind == "edit"
        )
    )
    assert entry is not None and entry.ok is True
    assert "Pumpp" in entry.what and "Pump" in entry.what
    assert entry.company_ids == [tenant.company_id]

    approved_child = await client.post(
        f"/proposals/{pump['id']}/approve", headers=tenant.governor.headers
    )
    assert approved_child.status_code == 200, approved_child.text
    child_ready = (
        await client.get(f"/proposals/{child['id']}", headers=tenant.governor.headers)
    ).json()
    assert child_ready["ready"] is True


async def test_edit_concept_action_normalises_and_changes_the_birth_relation(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    created = (
        await propose_concept(client, tenant, tenant.builder, "Valve", tenant.root_id)
    ).json()

    response = await _patch(
        client, created["id"], tenant.builder.headers, revision=0, action="  Controls  "
    )

    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["revision"] == 1
    assert edited["html"] == f"<b>Valve</b> <i>· {tenant.company_name} <b>controls</b> Valve</i>"
    assert edited["artefacts"]["relations"][0]["label"] == "controls"
    relation = await session.get(Relation, uuid.UUID(created["relationId"]))
    assert relation is not None
    await session.refresh(relation)
    assert relation.label == "controls"
    concept = await session.get(Concept, uuid.UUID(created["conceptId"]))
    assert concept is not None
    await session.refresh(concept)
    assert concept.birth_action == "controls"
    events = await _events(session, tenant, created["id"])
    assert {"proposal.changed", "relation.changed"} <= events

    both = await _patch(
        client,
        created["id"],
        tenant.builder.headers,
        revision=1,
        label="Gate valve",
        action="opens",
    )
    assert both.status_code == 200, both.text
    assert both.json()["revision"] == 2
    assert both.json()["title"] == "Gate valve"
    assert "<b>opens</b>" in both.json()["html"]


async def test_edit_spec_label_and_refuse_its_action(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    vehicle = await approved(client, tenant, "Vehicle", domain_key="logistics")
    spec = (
        await client.post(
            "/concepts",
            json={
                "type": "spec",
                "companyId": str(tenant.company_id),
                "parentId": vehicle["id"],
                "label": "Truk",
                "domainKey": "logistics",
            },
            headers=tenant.builder.headers,
        )
    ).json()

    response = await _patch(client, spec["id"], tenant.builder.headers, revision=0, label="Truck")

    assert response.status_code == 200, response.text
    assert response.json()["html"] == "<b>Truck</b> <i>is a Vehicle</i>"
    assert response.json()["title"] == "Truck"
    assert response.json()["artefacts"]["relations"][0]["label"] == "is a"

    refused = await _patch(client, spec["id"], tenant.builder.headers, revision=1, action="kind of")
    assert refused.status_code == 422
    assert refused.json()["code"] == "validation_failed"


async def test_edit_relation_action(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    order = await approved(client, tenant, "Order", domain_key="sales")
    item = await approved(client, tenant, "Item")
    relation = await _pending_relation(client, tenant, order["id"], item["id"], "containz")

    response = await _patch(
        client, relation["id"], tenant.builder.headers, revision=0, action="Contains"
    )

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Order contains Item"
    assert response.json()["html"] == "Order <b>contains</b> Item"
    assert response.json()["artefacts"]["relations"][0]["label"] == "contains"
    assert response.json()["revision"] == 1

    for forbidden_action in ("is a", "Equivalent   to"):
        refused = await _patch(
            client, relation["id"], tenant.builder.headers, revision=1, action=forbidden_action
        )
        assert refused.status_code == 422, refused.text
    labelled = await _patch(client, relation["id"], tenant.builder.headers, revision=1, label="X")
    assert labelled.status_code == 422
    empty = await _patch(client, relation["id"], tenant.builder.headers, revision=1)
    assert empty.status_code == 422


async def test_stale_revision_and_decided_proposals(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    created = (
        await propose_concept(client, tenant, tenant.builder, "Shift", tenant.root_id)
    ).json()

    stale = await _patch(client, created["id"], tenant.builder.headers, revision=4, label="Team")
    assert stale.status_code == 409
    assert stale.json()["code"] == "proposal_changed"

    edited = await _patch(client, created["id"], tenant.builder.headers, revision=0, label="Team")
    assert edited.status_code == 200, edited.text
    old_approval = await client.post(
        f"/proposals/{created['id']}/approve?expectedRevision=0", headers=tenant.governor.headers
    )
    assert old_approval.status_code == 409
    assert old_approval.json()["code"] == "proposal_changed"
    decided = await client.post(
        f"/proposals/{created['id']}/approve?expectedRevision=1", headers=tenant.governor.headers
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["proposal"]["revision"] == 1
    assert decided.json()["artefacts"]["concepts"][0]["label"] == "Team"

    after = await _patch(client, created["id"], tenant.builder.headers, revision=1, label="Crew")
    assert after.status_code == 409
    assert after.json()["code"] == "proposal_not_editable"


async def test_change_and_half_approved_proposals_are_not_editable(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    concept = await approved(client, tenant, "Invoice", domain_key="finance")
    settings = await session.get(TenantSettings, tenant.tenant_id)
    assert settings is not None
    settings.two_approvers = True
    await session.commit()
    try:
        rename = await client.patch(
            f"/concepts/{concept['id']}", json={"label": "Bill"}, headers=tenant.builder.headers
        )
        assert rename.status_code == 202, rename.text
        change_id = rename.json()["id"]
        pending = await _patch(client, change_id, tenant.builder.headers, revision=0, label="Note")
        assert pending.status_code == 409
        assert pending.json()["code"] == "proposal_not_editable"
        half = await client.post(f"/proposals/{change_id}/approve", headers=tenant.governor.headers)
        assert half.status_code == 200, half.text
        assert half.json()["proposal"]["state"] == "half_approved"
        edited = await _patch(client, change_id, tenant.builder.headers, revision=0, label="Note")
        assert edited.status_code == 409
        assert edited.json()["code"] == "proposal_not_editable"
    finally:
        settings.two_approvers = False
        await session.commit()


async def test_duplicate_label_is_refused(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    await approved(client, tenant, "Sensor", domain_key="maintenance")
    created = (
        await propose_concept(client, tenant, tenant.builder, "Probe", tenant.root_id)
    ).json()

    response = await _patch(
        client, created["id"], tenant.builder.headers, revision=0, label="sensor"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "duplicate_label"
    same_case = await _patch(
        client, created["id"], tenant.builder.headers, revision=0, label="PROBE"
    )
    assert same_case.status_code == 200, same_case.text
    assert same_case.json()["title"] == "PROBE"


async def test_who_may_edit(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    created = (await propose_concept(client, tenant, tenant.builder, "Line", tenant.root_id)).json()
    member = await scoped_user(session, tenant, RoleName.MEMBER, ScopeKind.TENANT)
    other = await add_company(client, tenant, "Elsewhere")
    other_builder = await scoped_user(
        session,
        tenant,
        RoleName.BUILDER,
        ScopeKind.COMPANY,
        company_id=uuid.UUID(other["company"]["id"]),
    )

    outsider = await _patch(client, created["id"], tenant.outsider.headers, revision=0, label="A")
    assert outsider.status_code == 404
    elsewhere = await _patch(client, created["id"], other_builder, revision=0, label="A")
    assert elsewhere.status_code == 404
    reader = await _patch(client, created["id"], member, revision=0, label="A")
    assert reader.status_code == 403
    by_owner = await _patch(client, created["id"], tenant.owner.headers, revision=0, label="Lane")
    assert by_owner.status_code == 200, by_owner.text
    by_proposer = await _patch(
        client, created["id"], tenant.builder.headers, revision=1, label="Track"
    )
    assert by_proposer.status_code == 200, by_proposer.text
    assert by_proposer.json()["revision"] == 2


async def test_edit_is_isolated_to_the_proposals_company(
    client: httpx.AsyncClient, tenant: TenantFixture, session: AsyncSession
) -> None:
    other = await add_company(client, tenant, "Isolated")
    created = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": other["company"]["id"],
            "parentId": other["root"]["id"],
            "label": "Far",
            "domainKey": "sales",
            "action": "has",
        },
        headers=tenant.builder.headers,
    )
    assert created.status_code == 202, created.text
    home_owner = await _patch(
        client, created.json()["id"], tenant.owner.headers, revision=0, label="Near"
    )
    assert home_owner.status_code == 404
    home_named = (
        await propose_concept(client, tenant, tenant.builder, "Far", tenant.root_id)
    ).json()
    edited = await _patch(
        client, created.json()["id"], tenant.builder.headers, revision=0, label="Near"
    )
    assert edited.status_code == 200, edited.text
    untouched = (
        await client.get(f"/proposals/{home_named['id']}", headers=tenant.governor.headers)
    ).json()
    assert untouched["title"] == "Far" and untouched["revision"] == 0
