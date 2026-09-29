"""POST /proposals/{proposalId}/approve-branch and `Proposal.openBelow`."""

from __future__ import annotations

import httpx
import pytest

from app.config import get_settings
from tests.conftest import TenantFixture
from tests.test_proposals import add_company, approved

pytestmark = pytest.mark.asyncio(loop_scope="session")


def concept(tenant: TenantFixture, label: str, parent: dict) -> dict:
    return {
        "type": "concept",
        "companyId": str(tenant.company_id),
        "label": label,
        "domainKey": "production",
        "action": "includes",
        **parent,
    }


async def tree(client: httpx.AsyncClient, tenant: TenantFixture) -> list[dict]:
    """Line under the root, Cell and Robot below it, and Robot feeds an approved Oven."""
    oven = await approved(client, tenant, "Oven")
    drafts = [
        concept(tenant, "Line", {"parentId": str(tenant.root_id)}),
        concept(tenant, "Cell", {"parentLabel": "Line"}),
        concept(tenant, "Robot", {"parentLabel": "Cell"}),
        {
            "type": "relation",
            "companyId": str(tenant.company_id),
            "aLabel": "Robot",
            "bId": oven["id"],
            "action": "feeds",
        },
    ]
    created = await client.post(
        "/proposals/batch", json={"drafts": drafts}, headers=tenant.builder.headers
    )
    assert created.status_code == 202, created.text
    return created.json()


async def open_below(client: httpx.AsyncClient, tenant: TenantFixture) -> dict[str, int]:
    listed = await client.get("/proposals", headers=tenant.governor.headers)
    assert listed.status_code == 200, listed.text
    return {p["title"]: p.get("openBelow", 0) for p in listed.json()["items"]}


async def test_a_branch_is_counted_and_approved_parents_first(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    line, cell, robot, feeds = await tree(client, tenant)

    assert await open_below(client, tenant) == {
        "Line": 3,
        "Cell": 2,
        "Robot": 1,
        "Robot feeds Oven": 0,
    }
    single = await client.get(f"/proposals/{cell['id']}", headers=tenant.governor.headers)
    assert single.json()["openBelow"] == 2

    result = await client.post(
        f"/proposals/{line['id']}/approve-branch", headers=tenant.governor.headers
    )

    assert result.status_code == 200, result.text
    assert result.json() == {
        "rootId": line["id"],
        "approved": 4,
        "skipped": 0,
        "remaining": 0,
        "batches": 1,
        "complete": True,
    }
    states = await client.get(
        "/proposals?filter[state]=approved&pageSize=100", headers=tenant.governor.headers
    )
    approved_titles = {p["title"] for p in states.json()["items"]}
    assert {"Line", "Cell", "Robot", "Robot feeds Oven"} <= approved_titles


async def test_branch_approval_runs_in_batches_and_continues_on_the_same_root(
    client: httpx.AsyncClient, tenant: TenantFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    line, *_ = await tree(client, tenant)
    monkeypatch.setenv("ONTAIX_BRANCH_APPROVE_BATCH", "1")
    monkeypatch.setenv("ONTAIX_BRANCH_APPROVE_MAX_ROUNDS", "2")
    get_settings.cache_clear()
    try:
        first = await client.post(
            f"/proposals/{line['id']}/approve-branch", headers=tenant.governor.headers
        )
        second = await client.post(
            f"/proposals/{line['id']}/approve-branch", headers=tenant.governor.headers
        )
    finally:
        monkeypatch.delenv("ONTAIX_BRANCH_APPROVE_BATCH")
        monkeypatch.delenv("ONTAIX_BRANCH_APPROVE_MAX_ROUNDS")
        get_settings.cache_clear()

    assert first.status_code == 200, first.text
    assert first.json() | {"rootId": None} == {
        "rootId": None,
        "approved": 2,
        "skipped": 0,
        "remaining": 2,
        "batches": 2,
        "complete": False,
    }
    assert second.status_code == 200, second.text
    assert (second.json()["approved"], second.json()["remaining"], second.json()["complete"]) == (
        2,
        0,
        True,
    )


async def test_a_branch_stays_in_its_company_and_rejects_other_roots(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    line, *_ = await tree(client, tenant)
    other = await add_company(client, tenant, "Other")
    foreign = await client.post(
        "/proposals/batch",
        json={
            "drafts": [
                {
                    "type": "concept",
                    "companyId": other["company"]["id"],
                    "parentId": other["root"]["id"],
                    "label": "Line",
                    "domainKey": "production",
                    "action": "has",
                },
                {
                    "type": "concept",
                    "companyId": other["company"]["id"],
                    "parentLabel": "Line",
                    "label": "Press",
                    "domainKey": "production",
                    "action": "has",
                },
            ]
        },
        headers=tenant.builder.headers,
    )
    assert foreign.status_code == 202, foreign.text

    counts = await client.get("/proposals", headers=tenant.governor.headers)
    below = {(p["title"], p["companyId"]): p.get("openBelow", 0) for p in counts.json()["items"]}
    assert below[("Line", str(tenant.company_id))] == 3
    assert below[("Line", other["company"]["id"])] == 1

    builder = await client.post(
        f"/proposals/{line['id']}/approve-branch", headers=tenant.builder.headers
    )
    assert builder.status_code == 403
    oven = await approved(client, tenant, "Kiln")
    rename = await client.patch(
        f"/concepts/{oven['id']}", json={"label": "Furnace"}, headers=tenant.builder.headers
    )
    assert rename.status_code == 202, rename.text
    change = await client.post(
        f"/proposals/{rename.json()['id']}/approve-branch", headers=tenant.governor.headers
    )
    assert change.status_code == 409 and change.json()["code"] == "branch_root_invalid"

    rejected = await client.post(
        f"/proposals/{line['id']}/reject", json={}, headers=tenant.governor.headers
    )
    assert rejected.status_code == 200
    decided = await client.post(
        f"/proposals/{line['id']}/approve-branch", headers=tenant.governor.headers
    )
    assert decided.status_code == 409 and decided.json()["code"] == "proposal_decided"
