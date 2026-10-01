"""`POST /deletion-impact`: what a deletion would remove, counted once and only when readable."""

from __future__ import annotations

import uuid

import httpx
import pytest

from tests.conftest import TenantFixture
from tests.test_mutations_are_proposals import approved_concept
from tests.test_proposals import add_company, approved, propose_concept

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _approved_child(
    client: httpx.AsyncClient,
    tenant: TenantFixture,
    company_id: str,
    parent_id: str,
    label: str,
    domain_key: str,
) -> dict:
    created = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": company_id,
            "parentId": parent_id,
            "label": label,
            "domainKey": domain_key,
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


async def _approved_relation(
    client: httpx.AsyncClient, tenant: TenantFixture, path: str, body: dict
) -> None:
    created = await client.post(path, json=body, headers=tenant.builder.headers)
    assert created.status_code == 202, created.text
    decided = await client.post(
        f"/proposals/{created.json()['id']}/approve", headers=tenant.governor.headers
    )
    assert decided.status_code == 200, decided.text


async def _tree(client: httpx.AsyncClient, tenant: TenantFixture) -> dict:
    """Assembly (production) > Bolt (quality) > Thread (quality) > pending Pitch (quality);
    Depot (logistics) related to Assembly; Assembly equivalent to Other's Part; one proposed
    attribute on Assembly."""
    home = str(tenant.company_id)
    assembly = await approved_concept(client, tenant, "Assembly", "production")
    bolt = await _approved_child(client, tenant, home, assembly["id"], "Bolt", "quality")
    thread = await _approved_child(client, tenant, home, bolt["id"], "Thread", "quality")
    pitch = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": home,
            "parentId": thread["id"],
            "label": "Pitch",
            "domainKey": "quality",
            "action": "has",
        },
        headers=tenant.builder.headers,
    )
    assert pitch.status_code == 202, pitch.text
    depot = await approved(client, tenant, "Depot", domain_key="logistics")
    await _approved_relation(
        client,
        tenant,
        "/relations",
        {"type": "relation", "aId": assembly["id"], "bId": depot["id"], "action": "stored in"},
    )
    other = await add_company(client, tenant, "Other")
    part = await _approved_child(
        client, tenant, other["company"]["id"], other["root"]["id"], "Part", "sales"
    )
    await _approved_relation(
        client, tenant, "/equivalences", {"aId": assembly["id"], "bId": part["id"]}
    )
    attribute = await client.post(
        "/proposals",
        json={
            "type": "attr",
            "conceptId": assembly["id"],
            "name": "weight",
            "attributeType": "number",
            "value": "3",
        },
        headers=tenant.builder.headers,
    )
    assert attribute.status_code == 202, attribute.text
    products = await client.get(
        f"/domain-products?companyId={home}", headers=tenant.governor.headers
    )
    quality = next(p for p in products.json() if p["key"] == "quality")
    return {
        "assembly": assembly,
        "bolt": bolt,
        "thread": thread,
        "pitch": pitch.json(),
        "depot": depot,
        "other": other,
        "part": part,
        "quality": quality,
    }


async def _impact(
    client: httpx.AsyncClient, headers: dict[str, str], **body: object
) -> httpx.Response:
    return await client.post("/deletion-impact", json=body, headers=headers)


async def test_impact_counts_descendants_relations_once_and_cross_company(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    tree = await _tree(client, tenant)
    home = str(tenant.company_id)

    one = await _impact(
        client, tenant.governor.headers, companyId=home, conceptIds=[tree["assembly"]["id"]]
    )

    assert one.status_code == 200, one.text
    assert one.json() == {
        "concepts": 1,
        "descendants": 3,
        "relations": 6,
        "crossCompanyRelations": 1,
        "bindings": 0,
        "attributes": 1,
        "sources": 0,
        "cascadedProposals": 2,
        "names": ["Assembly", "Bolt", "Thread", "Pitch"],
    }

    two = await _impact(
        client,
        tenant.governor.headers,
        companyId=home,
        conceptIds=[tree["assembly"]["id"], tree["bolt"]["id"]],
    )
    assert two.status_code == 200, two.text
    body = two.json()
    assert (body["concepts"], body["descendants"], body["relations"]) == (2, 2, 6)
    assert body["names"] == ["Assembly", "Bolt", "Thread", "Pitch"]

    product = await _impact(
        client, tenant.governor.headers, companyId=home, domainProductIds=[tree["quality"]["id"]]
    )
    assert product.status_code == 200, product.text
    body = product.json()
    assert (body["concepts"], body["descendants"], body["relations"]) == (3, 0, 3)
    assert body["crossCompanyRelations"] == 0
    assert body["cascadedProposals"] == 1
    assert set(body["names"]) == {"Bolt", "Thread", "Pitch"}

    mixed = await _impact(
        client,
        tenant.governor.headers,
        companyId=home,
        conceptIds=[tree["depot"]["id"]],
        domainProductIds=[tree["quality"]["id"]],
    )
    assert mixed.status_code == 200, mixed.text
    body = mixed.json()
    assert (body["concepts"], body["descendants"], body["relations"]) == (4, 0, 5)
    assert body["names"][0] == "Depot"


async def test_impact_of_a_whole_company(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    tree = await _tree(client, tenant)

    response = await _impact(
        client, tenant.governor.headers, companyId=tree["other"]["company"]["id"], wholeCompany=True
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["concepts"], body["descendants"]) == (1, 0)
    assert body["relations"] == 2
    assert body["crossCompanyRelations"] == 1
    assert body["sources"] == 0 and body["bindings"] == 0
    assert body["names"] == ["Part"]

    with_items = await _impact(
        client,
        tenant.governor.headers,
        companyId=tree["other"]["company"]["id"],
        wholeCompany=True,
        conceptIds=[tree["part"]["id"]],
    )
    assert with_items.status_code == 422


async def test_impact_names_at_most_six(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    root = await approved(client, tenant, "Fleet", domain_key="logistics")
    for n in range(7):
        created = await propose_concept(
            client,
            tenant,
            tenant.builder,
            f"Vehicle {n}",
            uuid.UUID(root["id"]),
            domain_key="logistics",
        )
        assert created.status_code == 202, created.text

    response = await _impact(
        client, tenant.governor.headers, companyId=str(tenant.company_id), conceptIds=[root["id"]]
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["concepts"] == 1 and body["descendants"] == 7
    assert len(body["names"]) == 6 and body["names"][0] == "Fleet"
    assert body["cascadedProposals"] == 7


async def test_impact_refuses_bad_targets(client: httpx.AsyncClient, tenant: TenantFixture) -> None:
    tree = await _tree(client, tenant)
    home = str(tenant.company_id)

    unknown = await _impact(
        client, tenant.governor.headers, companyId=home, conceptIds=[str(uuid.uuid4())]
    )
    assert unknown.status_code == 404
    spanning = await _impact(
        client, tenant.governor.headers, companyId=home, conceptIds=[tree["part"]["id"]]
    )
    assert spanning.status_code == 422
    assert spanning.json()["code"] == "validation_failed"
    root = await _impact(
        client, tenant.governor.headers, companyId=home, conceptIds=[str(tenant.root_id)]
    )
    assert root.status_code == 409
    assert root.json()["code"] == "root_concept"
    empty = await _impact(client, tenant.governor.headers, companyId=home)
    assert empty.status_code == 422
    twice = await _impact(
        client,
        tenant.governor.headers,
        companyId=home,
        conceptIds=[tree["depot"]["id"], tree["depot"]["id"]],
    )
    assert twice.status_code == 422
    too_many = await _impact(
        client,
        tenant.governor.headers,
        companyId=home,
        conceptIds=[str(uuid.uuid4()) for _ in range(201)],
    )
    assert too_many.status_code == 422
    outsider = await _impact(
        client, tenant.outsider.headers, companyId=home, conceptIds=[tree["depot"]["id"]]
    )
    assert outsider.status_code == 404
    other_owner = await _impact(
        client, tenant.owner.headers, companyId=tree["other"]["company"]["id"], wholeCompany=True
    )
    assert other_owner.status_code == 404
