"""Proposal lifecycle against a real PostgreSQL: propose, approve, second-approve, reject."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.models.storage.audit_entry import AuditEntry
from app.models.storage.concept import Concept
from app.models.storage.outbox import Outbox
from app.models.storage.relation import Relation
from app.models.storage.tenant_settings import TenantSettings
from tests.conftest import Persona, TenantFixture

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def propose_concept(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    persona: Persona,
    label: str,
    parent_id: uuid.UUID | None = None,
    parent_label: str | None = None,
    domain_key: str = "production",
) -> httpx.Response:
    body: dict = {
        "type": "concept",
        "companyId": str(tenant.company_id),
        "label": label,
        "domainKey": domain_key,
        "action": "operates",
    }
    if parent_id is not None:
        body["parentId"] = str(parent_id)
    if parent_label is not None:
        body["parentLabel"] = parent_label
    return await client.post("/concepts", json=body, headers=persona.headers)


async def approved(
    client: httpx.AsyncClient, tenant: TenantFixture, label: str, domain_key: str = "production"
) -> dict:
    """Propose a concept under the home root and approve it; returns the approved concept."""
    created = await propose_concept(
        client, tenant, tenant.builder, label, tenant.root_id, domain_key=domain_key
    )
    assert created.status_code == 202, created.text
    decided = await client.post(
        f"/proposals/{created.json()['id']}/approve", headers=tenant.governor.headers
    )
    assert decided.status_code == 200, decided.text
    return decided.json()["artefacts"]["concepts"][0]


async def add_company(client: httpx.AsyncClient, tenant: TenantFixture, name: str) -> dict:
    """A second company of the tenant, added by the Administrator."""
    created = await client.post(
        "/companies",
        json={"name": f"{name} {uuid.uuid4().hex[:6]}", "start": "one_cell"},
        headers=tenant.admin.headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


async def test_propose_returns_202_and_keeps_the_concept_pending(
    client: httpx.AsyncClient, tenant: TenantFixture, session
) -> None:
    response = await propose_concept(client, tenant, tenant.builder, "Plant", tenant.root_id)

    assert response.status_code == 202, response.text
    proposal = response.json()
    assert proposal["type"] == "concept"
    assert proposal["state"] == "pending"
    assert proposal["heading"] == "New concept · Production"
    assert proposal["why"] == "domain product: Production"
    assert proposal["ready"] is True
    assert proposal["artefacts"]["concepts"][0]["pending"] is True
    assert proposal["artefacts"]["relations"][0]["label"] == "operates"
    assert proposal["artefacts"]["relations"][0]["pending"] is True

    row = await session.get(Concept, uuid.UUID(proposal["conceptId"]))
    assert row is not None and row.pending is True
    assert row.parent_id == tenant.root_id
    assert row.birth_relation_id == uuid.UUID(proposal["relationId"])


async def test_approve_bumps_revision_and_writes_audit_and_outbox(
    client: httpx.AsyncClient, tenant: TenantFixture, session
) -> None:
    created = (
        await propose_concept(client, tenant, tenant.builder, "Machine", tenant.root_id)
    ).json()

    response = await client.post(
        f"/proposals/{created['id']}/approve", headers=tenant.governor.headers
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["proposal"]["state"] == "approved"
    assert result["proposal"]["approvals"][0]["userId"] == str(tenant.governor.user_id)
    assert result["artefacts"]["concepts"][0]["pending"] is False
    assert result["artefacts"]["domainProducts"][0]["revision"] >= 1
    assert result["artefacts"]["domainProducts"][0]["version"].startswith("v1.")
    assert result["audit"]["kind"] == "concept"
    assert result["audit"]["what"] == "Machine"
    assert result["audit"]["ok"] is True

    audit_rows = (
        await session.scalars(
            select(AuditEntry).where(AuditEntry.proposal_id == uuid.UUID(created["id"]))
        )
    ).all()
    assert [a.ok for a in audit_rows] == [True]
    events = (
        await session.scalars(
            select(Outbox).where(Outbox.tenant_id == tenant.tenant_id).order_by(Outbox.id)
        )
    ).all()
    actions = {(e.aggregate, e.action) for e in events}
    assert {("proposal", "created"), ("concept", "born"), ("proposal", "approved")} <= actions
    assert ("domain_product", "changed") in actions
    assert ("audit", "appended") in actions
    assert all(e.subject == f"ontaix.{tenant.tenant_id}.{e.aggregate}.{e.action}" for e in events)

    scene = (await client.get("/scene", headers=tenant.governor.headers)).json()
    product = next(p for p in scene["companies"][0]["domainProducts"] if p["key"] == "production")
    assert product["revision"] == result["artefacts"]["domainProducts"][0]["revision"]


async def test_builder_cannot_approve(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    created = (
        await propose_concept(client, tenant, tenant.builder, "Shift", tenant.root_id)
    ).json()

    response = await client.post(
        f"/proposals/{created['id']}/approve", headers=tenant.builder.headers
    )

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "forbidden"
    assert response.json()["type"] == "urn:ontaix:problem:forbidden"


async def test_owner_in_company_scope_can_approve(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    created = (
        await propose_concept(client, tenant, tenant.builder, "Operator", tenant.root_id)
    ).json()

    response = await client.post(
        f"/proposals/{created['id']}/approve", headers=tenant.owner.headers
    )

    assert response.status_code == 200, response.text


async def test_blocked_proposal_cannot_be_approved_before_its_parent(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    parent = (
        await propose_concept(client, tenant, tenant.builder, "Warehouse", tenant.root_id)
    ).json()
    child = (
        await propose_concept(
            client,
            tenant,
            tenant.builder,
            "Stock level",
            parent_label="Warehouse",
            domain_key="supply",
        )
    ).json()
    assert child["ready"] is False
    assert child["waitFor"] == "Warehouse"

    blocked = await client.post(
        f"/proposals/{child['id']}/approve", headers=tenant.governor.headers
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "proposal_not_ready"

    assert (
        await client.post(f"/proposals/{parent['id']}/approve", headers=tenant.governor.headers)
    ).status_code == 200
    unblocked = await client.post(
        f"/proposals/{child['id']}/approve", headers=tenant.governor.headers
    )
    assert unblocked.status_code == 200


async def test_reject_cascades_to_descendants(
    client: httpx.AsyncClient, tenant: TenantFixture, session
) -> None:
    parent = (
        await propose_concept(
            client, tenant, tenant.builder, "Customer", tenant.root_id, domain_key="sales"
        )
    ).json()
    child = (
        await propose_concept(
            client, tenant, tenant.builder, "Quotation", parent_label="Customer", domain_key="sales"
        )
    ).json()
    grandchild = (
        await propose_concept(
            client,
            tenant,
            tenant.builder,
            "Sales order",
            parent_label="Quotation",
            domain_key="sales",
        )
    ).json()

    response = await client.post(
        f"/proposals/{parent['id']}/reject", headers=tenant.governor.headers
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["proposal"]["state"] == "rejected"
    assert {p["id"] for p in result["cascaded"]} == {child["id"], grandchild["id"]}
    assert result["caption"].startswith("Customer was not kept.")
    assert result["audit"]["ok"] is False
    for proposal_id in (parent["id"], child["id"], grandchild["id"]):
        state = (
            await client.get(f"/proposals/{proposal_id}", headers=tenant.governor.headers)
        ).json()
        assert state["state"] == "rejected"
    for concept_id in (parent["conceptId"], child["conceptId"], grandchild["conceptId"]):
        assert await session.get(Concept, uuid.UUID(concept_id)) is None


async def test_second_approver_must_differ(
    client: httpx.AsyncClient, tenant: TenantFixture, session
) -> None:
    settings = await session.get(TenantSettings, tenant.tenant_id)
    assert settings is not None
    settings.two_approvers = True
    await session.commit()
    try:
        created = (
            await propose_concept(
                client, tenant, tenant.builder, "Invoice", tenant.root_id, domain_key="finance"
            )
        ).json()
        assert (
            await client.post(
                f"/proposals/{created['id']}/approve", headers=tenant.governor.headers
            )
        ).status_code == 200
        rename = await client.patch(
            f"/concepts/{created['conceptId']}",
            json={"label": "Bill"},
            headers=tenant.builder.headers,
        )
        assert rename.status_code == 202, rename.text
        change_id = rename.json()["id"]

        first = await client.post(
            f"/proposals/{change_id}/approve", headers=tenant.governor.headers
        )
        assert first.status_code == 200, first.text
        assert first.json()["proposal"]["state"] == "half_approved"
        assert first.json()["proposal"]["why"].endswith(
            "1 of 2 approvals · a Governor must approve too"
        )

        same = await client.post(
            f"/proposals/{change_id}/second-approve", headers=tenant.governor.headers
        )
        assert same.status_code == 409
        assert same.json()["code"] == "same_approver"

        other = await client.post(
            f"/proposals/{change_id}/second-approve", headers=tenant.second_governor.headers
        )
        assert other.status_code == 200, other.text
        assert other.json()["proposal"]["state"] == "approved"
        assert other.json()["artefacts"]["concepts"][0]["label"] == "Bill"
        assert [a["ordinal"] for a in other.json()["proposal"]["approvals"]] == [1, 2]
    finally:
        settings.two_approvers = False
        await session.commit()


async def test_second_approve_requires_half_approved_state(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    created = (
        await propose_concept(
            client, tenant, tenant.builder, "Budget", tenant.root_id, domain_key="finance"
        )
    ).json()

    response = await client.post(
        f"/proposals/{created['id']}/second-approve", headers=tenant.governor.headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "proposal_not_half_approved"


async def test_duplicate_label_is_refused(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    assert (
        await propose_concept(
            client, tenant, tenant.builder, "Carrier", tenant.root_id, domain_key="logistics"
        )
    ).status_code == 202

    response = await propose_concept(client, tenant, tenant.builder, "carrier", tenant.root_id)

    assert response.status_code == 409
    assert response.json()["code"] == "duplicate_label"


async def test_batch_creates_in_order_and_later_drafts_see_earlier_labels(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    body = {
        "drafts": [
            {
                "type": "concept",
                "companyId": str(tenant.company_id),
                "parentId": str(tenant.root_id),
                "label": "Specification",
                "domainKey": "engineering",
                "action": "specified by",
            },
            {
                "type": "concept",
                "companyId": str(tenant.company_id),
                "parentLabel": "Specification",
                "label": "Test",
                "domainKey": "engineering",
                "action": "validated by",
            },
            {
                "type": "relation",
                "aLabel": "Test",
                "bLabel": "Specification",
                "companyId": str(tenant.company_id),
                "action": "checks",
            },
        ]
    }

    response = await client.post("/proposals/batch", json=body, headers=tenant.builder.headers)

    assert response.status_code == 202, response.text
    proposals = response.json()
    assert [p["type"] for p in proposals] == ["concept", "concept", "relation"]
    assert proposals[1]["ready"] is False
    assert proposals[2]["ready"] is False
    assert proposals[2]["waitFor"] == "Test and Specification"


async def test_approve_all_repeats_until_nothing_is_ready(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    (
        await propose_concept(
            client, tenant, tenant.builder, "Delivery", tenant.root_id, domain_key="logistics"
        )
    ).json()
    (
        await propose_concept(
            client,
            tenant,
            tenant.builder,
            "Shipment",
            parent_label="Delivery",
            domain_key="logistics",
        )
    ).json()

    response = await client.post("/proposals/approve-all", headers=tenant.governor.headers)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["approved"] >= 2
    assert result["rounds"] >= 2
    assert result["caption"] == "All pending proposals are now part of the model."
    open_page = (await client.get("/proposals", headers=tenant.governor.headers)).json()
    assert open_page["total"] == 0


async def test_approve_all_skips_proposals_outside_the_callers_scope(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    other = await add_company(client, tenant, "Outside")
    home = (
        await propose_concept(
            client, tenant, tenant.builder, "Route", tenant.root_id, domain_key="logistics"
        )
    ).json()
    foreign = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": other["company"]["id"],
            "parentId": other["root"]["id"],
            "label": "Lane",
            "domainKey": "logistics",
            "action": "has",
        },
        headers=tenant.builder.headers,
    )
    assert foreign.status_code == 202, foreign.text

    response = await client.post("/proposals/approve-all", headers=tenant.owner.headers)

    assert response.status_code == 200, response.text
    assert response.json()["approved"] == 1
    assert response.json()["remaining"] >= 1
    states = {
        pid: (await client.get(f"/proposals/{pid}", headers=tenant.governor.headers)).json()[
            "state"
        ]
        for pid in (home["id"], foreign.json()["id"])
    }
    assert states == {home["id"]: "approved", foreign.json()["id"]: "pending"}


@pytest.mark.parametrize("bulk", ["approve-all", "reject-all"])
async def test_bulk_decisions_are_forbidden_without_an_approving_role(
    client: httpx.AsyncClient, tenant: TenantFixture, bulk: str
) -> None:
    created = (
        await propose_concept(
            client, tenant, tenant.builder, "Pallet", tenant.root_id, domain_key="logistics"
        )
    ).json()

    response = await client.post(f"/proposals/{bulk}", headers=tenant.builder.headers)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "forbidden"
    still_open = (
        await client.get(f"/proposals/{created['id']}", headers=tenant.governor.headers)
    ).json()
    assert still_open["state"] == "pending"


@pytest.mark.parametrize("kind", ["remove", "edit"])
async def test_rejecting_a_relation_change_keeps_the_approved_relation(
    client: httpx.AsyncClient, tenant: TenantFixture, kind: str
) -> None:
    a = await approved(client, tenant, f"Employee {kind}", domain_key="people")
    b = await approved(client, tenant, f"Training {kind}", domain_key="people")
    relation = await client.post(
        "/relations",
        json={"type": "relation", "aId": a["id"], "bId": b["id"], "action": "attends"},
        headers=tenant.builder.headers,
    )
    assert relation.status_code == 202, relation.text
    relation_id = relation.json()["relationId"]
    assert (
        await client.post(
            f"/proposals/{relation.json()['id']}/approve", headers=tenant.governor.headers
        )
    ).status_code == 200
    if kind == "remove":
        change = await client.delete(f"/relations/{relation_id}", headers=tenant.builder.headers)
    else:
        change = await client.patch(
            f"/relations/{relation_id}",
            json={"action": "completes"},
            headers=tenant.builder.headers,
        )
    assert change.status_code == 202, change.text

    rejected = await client.post(
        f"/proposals/{change.json()['id']}/reject", headers=tenant.governor.headers
    )

    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["proposal"]["state"] == "rejected"
    after = await client.get(f"/relations/{relation_id}", headers=tenant.governor.headers)
    assert after.status_code == 200, after.text
    assert after.json()["label"] == "attends"
    assert after.json()["pending"] is False


async def test_reject_cascades_to_relations_touching_the_concept(
    client: httpx.AsyncClient, tenant: TenantFixture, session
) -> None:
    anchor = await approved(client, tenant, "Supplier", domain_key="supply")
    pending = (
        await propose_concept(
            client, tenant, tenant.builder, "Contract", tenant.root_id, domain_key="supply"
        )
    ).json()
    relation = await client.post(
        "/relations",
        json={
            "type": "relation",
            "aId": anchor["id"],
            "bId": pending["conceptId"],
            "action": "signs",
        },
        headers=tenant.builder.headers,
    )
    assert relation.status_code == 202, relation.text

    response = await client.post(
        f"/proposals/{pending['id']}/reject", headers=tenant.governor.headers
    )

    assert response.status_code == 200, response.text
    assert [p["id"] for p in response.json()["cascaded"]] == [relation.json()["id"]]
    assert await session.get(Relation, uuid.UUID(relation.json()["relationId"])) is None
    assert await session.get(Concept, uuid.UUID(anchor["id"])) is not None


async def test_finalise_all_reports_counts(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.post("/proposals/finalise-all", headers=tenant.governor.headers)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["companies"] == 1
    assert result["scenesPlayed"] == 0
    assert result["caption"].endswith("Everything approved.")


async def test_unknown_user_is_unauthorized(client: httpx.AsyncClient) -> None:
    response = await client.get("/scene", headers={"X-Ontaix-User": "nobody@nowhere.test"})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_missing_header_is_unauthorized(client: httpx.AsyncClient) -> None:
    response = await client.get("/scene")

    assert response.status_code == 401
