"""Every ontology mutation endpoint answers 202 with a Proposal and never writes an approved row."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.models.storage.concept import Concept
from app.models.storage.relation import Relation
from tests.conftest import TenantFixture

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def approved_concept(
    client: httpx.AsyncClient, tenant: TenantFixture, label: str, domain_key: str = "production"
) -> dict:
    created = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": str(tenant.company_id),
            "parentId": str(tenant.root_id),
            "label": label,
            "domainKey": domain_key,
            "action": "has",
        },
        headers=tenant.builder.headers,
    )
    assert created.status_code == 202, created.text
    approved = await client.post(
        f"/proposals/{created.json()['id']}/approve", headers=tenant.governor.headers
    )
    assert approved.status_code == 200, approved.text
    return approved.json()["artefacts"]["concepts"][0]


async def test_spec_proposal_creates_pending_isa(
    client: httpx.AsyncClient, tenant: TenantFixture, session
) -> None:
    machine = await approved_concept(client, tenant, "Pump")

    response = await client.post(
        "/concepts",
        json={
            "type": "spec",
            "companyId": str(tenant.company_id),
            "parentId": machine["id"],
            "label": "Pump due for maintenance",
            "rule": "> 5,000 h since last service",
            "domainKey": "maintenance",
        },
        headers=tenant.builder.headers,
    )

    assert response.status_code == 202, response.text
    proposal = response.json()
    assert proposal["type"] == "spec"
    assert proposal["heading"] == "Specialisation · Maintenance"
    assert proposal["why"] == "rule: > 5,000 h since last service · domain product: Maintenance"
    relation = proposal["artefacts"]["relations"][0]
    assert relation["kind"] == "isa"
    assert relation["label"] == "is a"
    assert relation["aId"] == proposal["conceptId"]
    assert relation["bId"] == machine["id"]
    assert relation["rest"] == 300.0
    row = await session.get(Relation, uuid.UUID(relation["id"]))
    assert row is not None and row.pending is True


async def test_relation_proposal_is_pending_until_approved(
    client: httpx.AsyncClient, tenant: TenantFixture, session
) -> None:
    a = await approved_concept(client, tenant, "Order", "sales")
    b = await approved_concept(client, tenant, "Item", "production")

    response = await client.post(
        "/relations",
        json={"type": "relation", "aId": a["id"], "bId": b["id"], "action": "contains"},
        headers=tenant.builder.headers,
    )

    assert response.status_code == 202, response.text
    proposal = response.json()
    assert proposal["type"] == "relation"
    assert proposal["heading"] == "Relation"
    assert proposal["why"] == "across domain products: Sales → Production"
    assert proposal["ready"] is True
    row = await session.get(Relation, uuid.UUID(proposal["relationId"]))
    assert row is not None and row.pending is True

    duplicate = await client.post(
        "/relations",
        json={"type": "relation", "aId": a["id"], "bId": b["id"], "action": "Contains"},
        headers=tenant.builder.headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "duplicate_relation"


async def test_rename_is_a_change_proposal_and_does_not_touch_the_row(
    client: httpx.AsyncClient, tenant: TenantFixture, session
) -> None:
    concept = await approved_concept(client, tenant, "Sensor", "maintenance")

    response = await client.patch(
        f"/concepts/{concept['id']}", json={"label": "Probe"}, headers=tenant.builder.headers
    )

    assert response.status_code == 202, response.text
    proposal = response.json()
    assert proposal["type"] == "change"
    assert proposal["changeKind"] == "rename"
    assert proposal["title"] == "Rename Sensor to Probe"
    assert proposal["html"] == "Rename <b>Sensor</b> to <b>Probe</b>"
    row = await session.get(Concept, uuid.UUID(concept["id"]))
    assert row is not None and row.label == "Sensor"

    approved = await client.post(
        f"/proposals/{proposal['id']}/approve", headers=tenant.governor.headers
    )
    assert approved.status_code == 200
    await session.refresh(row)
    assert row.label == "Probe"


async def test_delete_concept_proposal_and_approval_removes_descendants(
    client: httpx.AsyncClient, tenant: TenantFixture, session
) -> None:
    parent = await approved_concept(client, tenant, "Inspection", "quality")
    child_created = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": str(tenant.company_id),
            "parentId": parent["id"],
            "label": "Defect",
            "domainKey": "quality",
            "action": "records",
        },
        headers=tenant.builder.headers,
    )
    child_id = child_created.json()["conceptId"]
    assert (
        await client.post(
            f"/proposals/{child_created.json()['id']}/approve", headers=tenant.governor.headers
        )
    ).status_code == 200

    response = await client.delete(f"/concepts/{parent['id']}", headers=tenant.builder.headers)

    assert response.status_code == 202, response.text
    proposal = response.json()
    assert proposal["changeKind"] == "delete_concept"
    assert proposal["title"] == "Delete Inspection"
    assert proposal["color"] == "#d95a68"
    assert await session.get(Concept, uuid.UUID(parent["id"])) is not None

    approved = await client.post(
        f"/proposals/{proposal['id']}/approve", headers=tenant.governor.headers
    )
    assert approved.status_code == 200, approved.text
    dying = {c["id"] for c in approved.json()["artefacts"]["concepts"]}
    assert dying == {parent["id"], child_id}
    session.expire_all()
    assert await session.get(Concept, uuid.UUID(parent["id"])) is None
    assert await session.get(Concept, uuid.UUID(child_id)) is None


async def test_relation_edit_and_remove_are_change_proposals(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    a = await approved_concept(client, tenant, "Employee", "people")
    b = await approved_concept(client, tenant, "Training", "people")
    relation = (
        await client.post(
            "/relations",
            json={"type": "relation", "aId": a["id"], "bId": b["id"], "action": "attends"},
            headers=tenant.builder.headers,
        )
    ).json()
    assert (
        await client.post(f"/proposals/{relation['id']}/approve", headers=tenant.governor.headers)
    ).status_code == 200

    edit = await client.patch(
        f"/relations/{relation['relationId']}",
        json={"action": "completes", "reverse": True},
        headers=tenant.builder.headers,
    )
    assert edit.status_code == 202, edit.text
    assert edit.json()["changeKind"] == "edit_relation"
    assert edit.json()["title"] == "Training completes Employee"
    assert edit.json()["why"] == "direction reversed"

    remove = await client.delete(
        f"/relations/{relation['relationId']}", headers=tenant.builder.headers
    )
    assert remove.status_code == 202, remove.text
    assert remove.json()["changeKind"] == "remove_relation"
    assert remove.json()["why"] == "action removed from the model"

    unchanged = (
        await client.get(f"/relations/{relation['relationId']}", headers=tenant.governor.headers)
    ).json()
    assert unchanged["label"] == "attends"
    assert unchanged["aId"] == a["id"]


async def test_structural_relation_cannot_be_relabelled(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    parent = await approved_concept(client, tenant, "Vehicle", "logistics")
    spec = (
        await client.post(
            "/concepts",
            json={
                "type": "spec",
                "companyId": str(tenant.company_id),
                "parentId": parent["id"],
                "label": "Truck",
                "domainKey": "logistics",
            },
            headers=tenant.builder.headers,
        )
    ).json()
    assert (
        await client.post(f"/proposals/{spec['id']}/approve", headers=tenant.governor.headers)
    ).status_code == 200

    response = await client.patch(
        f"/relations/{spec['relationId']}",
        json={"action": "kind of"},
        headers=tenant.builder.headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "structural_relation"


async def test_labels_are_html_escaped_in_panel_markup(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": str(tenant.company_id),
            "parentId": str(tenant.root_id),
            "label": "<script>alert(1)</script>",
            "domainKey": "production",
            "action": "has & holds",
            "seed": 0.25,
        },
        headers=tenant.builder.headers,
    )

    assert response.status_code == 202, response.text
    proposal = response.json()
    assert "<script>" not in proposal["html"]
    assert "&lt;script&gt;" in proposal["html"]
    assert "<b>has &amp; holds</b>" in proposal["html"]
    assert "<em>" not in proposal["html"]
    assert proposal["artefacts"]["relations"][0]["seed"] == 0.25


async def test_finalise_all_needs_governor_at_tenant_scope(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.post("/proposals/finalise-all", headers=tenant.owner.headers)

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


async def test_starter_vocabulary_is_proposed_by_system(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.post(
        "/companies",
        json={"name": f"Aurora {tenant.slug}", "sub": "valves", "start": "starter_vocabulary"},
        headers=tenant.admin.headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["company"]["isHome"] is False
    assert body["root"]["kind"] == "root"
    assert len(body["proposals"]) == 13
    assert {p["proposer"]["kind"] for p in body["proposals"]} == {"system"}
    assert body["proposals"][0]["caption"].endswith("’s Production.")

    denied = await client.post(
        "/companies",
        json={"name": "Nope", "start": "one_cell"},
        headers=tenant.builder.headers,
    )
    assert denied.status_code == 403


async def test_home_company_cannot_be_removed(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.delete(
        f"/companies/{tenant.company_id}", headers=tenant.builder.headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "home_company"


async def test_root_cannot_be_deleted(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    response = await client.delete(f"/concepts/{tenant.root_id}", headers=tenant.builder.headers)

    assert response.status_code == 409
    assert response.json()["code"] == "root_concept"


async def test_bindings_module_drafts_are_unavailable(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.post(
        "/proposals",
        json={
            "type": "source",
            "companyId": str(tenant.company_id),
            "label": "SAP ERP",
            "kindText": "ERP",
        },
        headers=tenant.builder.headers,
    )

    assert response.status_code == 503
    assert response.json()["code"] == "unavailable"


async def test_validation_errors_are_problems(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.post(
        "/concepts", json={"type": "concept", "label": ""}, headers=tenant.builder.headers
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    assert body["errors"]


async def test_unknown_filter_field_is_bad_request(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.get("/concepts?filter[colour]=red", headers=tenant.governor.headers)

    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"
