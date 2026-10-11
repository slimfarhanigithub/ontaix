"""The scene snapshot after the fixture seed, and tenant isolation between two tenants."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from app.clients import db_client
from app.seed import aurora, directory, northwind
from app.services.seed_service import seed_demo_tenant
from tests.conftest import TenantFixture

pytestmark = pytest.mark.asyncio(loop_scope="session")

SEED_HEADERS = {"X-Ontaix-User": directory.APPROVER_EMAIL}


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def demo_seeded(migrated_database: str) -> bool:
    """Seed the demo tenant once per module and prove a second run changes nothing."""
    async with db_client.get_platform_session_factory()() as s:
        created = await seed_demo_tenant(s)
        await s.commit()
    async with db_client.get_platform_session_factory()() as s:
        assert await seed_demo_tenant(s) is False
    return created


async def test_scene_returns_both_seeded_companies(
    client: httpx.AsyncClient, demo_seeded: bool
) -> None:
    response = await client.get("/scene", headers=SEED_HEADERS)

    assert response.status_code == 200, response.text
    scene = response.json()
    names = [c["name"] for c in scene["companies"]]
    assert names == [northwind.COMPANY_NAME, aurora.COMPANY_NAME]
    home, acquired = scene["companies"]
    assert home["isHome"] is True and acquired["isHome"] is False
    assert home["key"] == "northwind-industries" and acquired["key"] == "aurora-valves"

    expected_northwind = sum(
        1 for b in northwind.BATCHES for r in b.rows if not isinstance(r, northwind.RelationRow)
    )
    assert home["counts"]["concepts"] == expected_northwind
    assert acquired["counts"]["concepts"] == 13
    assert home["counts"]["equivalences"] == len(aurora.EQUIVALENCES)
    assert acquired["counts"]["equivalences"] == len(aurora.EQUIVALENCES)
    assert len(home["domainProducts"]) == 9
    production = next(p for p in home["domainProducts"] if p["key"] == "production")
    assert production["version"] == f"v1.{production['revision']}"
    assert production["revision"] > 0

    labels = {n["label"] for n in scene["nodes"]}
    assert {"Plant", "Machine due for maintenance", "Site", "Ledger entry"} <= labels
    assert all(n["pending"] is False for n in scene["nodes"])
    spec = next(n for n in scene["nodes"] if n["label"] == "Machine due for maintenance")
    assert spec["rule"] == "> 5,000 h since last service"
    assert spec["isSpecialisation"] is True
    assert spec["domainKey"] == "maintenance"
    same = [link for link in scene["links"] if link["kind"] == "same"]
    assert len(same) == len(aurora.EQUIVALENCES)
    assert all(len(link["companyIds"]) == 2 for link in same)
    assert scene["proposals"] == []
    assert "demoStory" not in scene["settings"]
    assert scene["settings"]["approvalRequired"] is True
    assert scene["appearance"]["colors"]["production"] == "#d30c55"
    assert len(scene["connectors"]) == 15
    assert "demoStory" not in scene
    assert scene["viewState"] == {"coverage": False}
    assert scene["sequence"] > 0


async def test_seeded_lineage_and_lists(client: httpx.AsyncClient, demo_seeded: bool) -> None:
    scene = (await client.get("/scene", headers=SEED_HEADERS)).json()
    product = next(n for n in scene["nodes"] if n["label"] == "Product")

    lineage = (await client.get(f"/concepts/{product['id']}/lineage", headers=SEED_HEADERS)).json()
    assert [a["label"] for a in lineage["ancestors"]] == [
        northwind.COMPANY_NAME,
        "Plant",
        "Production line",
        "Work order",
    ]
    assert lineage["ancestors"][0]["how"] == "the company"
    assert lineage["ancestors"][1]["how"] == "Northwind Industries operates Plant"
    assert lineage["caption"].startswith(
        "Northwind Industries → Plant → Production line → Work order → Product"
    )

    home_id = next(c["id"] for c in scene["companies"] if c["isHome"])
    concepts = (
        await client.get(
            f"/concepts?filter[domainKey]=production&filter[companyId]={home_id}&sort=label",
            headers=SEED_HEADERS,
        )
    ).json()
    assert concepts["total"] == 7
    assert [c["label"] for c in concepts["items"]][:2] == ["Machine", "Operator"]

    relations = (
        await client.get("/relations?filter[kind]=same&pageSize=5", headers=SEED_HEADERS)
    ).json()
    assert relations["total"] == 9 and len(relations["items"]) == 5
    equivalences = (await client.get("/equivalences", headers=SEED_HEADERS)).json()
    assert {e["aLabel"] for e in equivalences} == {a for a, _ in aurora.EQUIVALENCES}

    audit = (await client.get("/audit?pageSize=5", headers=SEED_HEADERS)).json()
    assert audit["total"] > 0
    assert all(e["ok"] is True for e in audit["items"])
    assert audit["items"][0]["actor"]["name"] == "Hugo Brandt"


async def test_seed_auditor_reads_and_builder_cannot_bulk_approve(
    client: httpx.AsyncClient, demo_seeded: bool
) -> None:
    auditor = (
        await client.get("/scene", headers={"X-Ontaix-User": "felix.grau@northwind.com"})
    ).json()
    assert len(auditor["companies"]) == 2

    builder_only = await client.post(
        "/proposals/approve-all", headers={"X-Ontaix-User": "tom.reiss@northwind.com"}
    )
    assert builder_only.status_code == 403
    assert builder_only.json()["code"] == "forbidden"


async def test_tenant_isolation(
    client: httpx.AsyncClient, tenant: TenantFixture, demo_seeded: bool
) -> None:
    demo = (await client.get("/scene", headers=SEED_HEADERS)).json()
    other = (await client.get("/scene", headers=tenant.governor.headers)).json()

    assert {c["id"] for c in demo["companies"]}.isdisjoint({c["id"] for c in other["companies"]})
    assert other["companies"][0]["name"] == tenant.company_name
    assert northwind.COMPANY_NAME not in {c["name"] for c in other["companies"]}

    demo_plant = next(n for n in demo["nodes"] if n["label"] == "Plant")
    cross_read = await client.get(f"/concepts/{demo_plant['id']}", headers=tenant.governor.headers)
    assert cross_read.status_code == 404
    cross_lineage = await client.get(
        f"/concepts/{demo_plant['id']}/lineage", headers=tenant.governor.headers
    )
    assert cross_lineage.status_code == 404
    cross_company = await client.get(
        f"/companies/{demo['companies'][0]['id']}", headers=tenant.governor.headers
    )
    assert cross_company.status_code == 404

    cross_propose = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": demo["companies"][0]["id"],
            "parentId": demo_plant["id"],
            "label": "Intruder",
            "domainKey": "production",
            "action": "has",
        },
        headers=tenant.builder.headers,
    )
    assert cross_propose.status_code == 404

    demo_proposals = (
        await client.get("/proposals?filter[state]=approved", headers=SEED_HEADERS)
    ).json()
    assert demo_proposals["total"] > 0
    cross_proposal = await client.get(
        f"/proposals/{demo_proposals['items'][0]['id']}", headers=tenant.governor.headers
    )
    assert cross_proposal.status_code == 404

    outsider = await client.get("/scene", headers=tenant.outsider.headers)
    assert outsider.status_code == 403
    assert outsider.json()["code"] == "forbidden"
