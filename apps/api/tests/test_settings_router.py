"""`/settings`: the read, the immediate audited change, the locked settings, and the
companies-may-interact switch with its confirmation."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import CompanyMode
from app.models.storage.tenant_settings import TenantSettings
from app.repositories import organization_settings_repository
from tests.auth_helpers import (
    create_member,
    create_organization,
    group_ids,
    ready_member,
    signed_in,
)
from tests.conftest import TEST_ORIGIN, AccountFixture, Browser, TenantFixture, make_tenant
from tests.test_proposals import add_company, approved

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def audit_texts(client: httpx.AsyncClient, tenant: TenantFixture) -> list[str]:
    response = await client.get("/audit?pageSize=200", headers=tenant.admin.headers)
    assert response.status_code == 200, response.text
    return [e["what"] for e in response.json()["items"]]


async def foreign_concept(client: httpx.AsyncClient, tenant: TenantFixture, other: dict) -> dict:
    created = await client.post(
        "/concepts",
        json={
            "type": "concept",
            "companyId": other["company"]["id"],
            "parentId": other["root"]["id"],
            "label": f"Client {uuid.uuid4().hex[:4]}",
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
    return decided.json()["artefacts"]["concepts"][0]


async def cross_company_relation(
    client: httpx.AsyncClient, tenant: TenantFixture, *, approve: bool
) -> dict:
    """A relation between the home company and a new one; approved or left pending."""
    other = await add_company(client, tenant, "Other")
    home = await approved(client, tenant, f"Customer {uuid.uuid4().hex[:4]}", domain_key="sales")
    foreign = await foreign_concept(client, tenant, other)
    created = await client.post(
        "/relations",
        json={"type": "relation", "aId": home["id"], "bId": foreign["id"], "action": "buys from"},
        headers=tenant.builder.headers,
    )
    assert created.status_code == 202, created.text
    proposal = created.json()
    if approve:
        decided = await client.post(
            f"/proposals/{proposal['id']}/approve", headers=tenant.governor.headers
        )
        assert decided.status_code == 200, decided.text
    return proposal


async def test_settings_are_read_by_any_role_and_match_the_scene(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.get("/settings", headers=tenant.builder.headers)
    scene = await client.get("/scene", headers=tenant.builder.headers)

    assert response.status_code == 200, response.text
    assert response.json() == scene.json()["settings"]
    assert response.json()["companyMode"] == "multiple"
    assert response.json()["approvalRequired"] is True
    assert (await client.get("/settings", headers=tenant.outsider.headers)).status_code == 403


async def test_administrator_changes_settings_with_one_audit_entry_per_key(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    response = await client.patch(
        "/settings",
        json={"voice": False, "refresh": "1 h", "llmMonthlyTokenCap": 5000},
        headers=tenant.admin.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["voice"] is False
    assert body["refresh"] == "1 h"
    assert body["llmMonthlyTokenCap"] == 5000
    read = await client.get("/settings", headers=tenant.admin.headers)
    assert read.json() == body
    texts = await audit_texts(client, tenant)
    assert "voice disabled" in texts
    assert "refresh interval 1 h" in texts
    assert "llmMonthlyTokenCap set to 5000" in texts

    restored = await client.patch(
        "/settings",
        json={"voice": True, "refresh": "15 min", "llmMonthlyTokenCap": 2000000},
        headers=tenant.admin.headers,
    )
    assert restored.status_code == 200, restored.text
    assert "voice enabled" in await audit_texts(client, tenant)


async def test_other_roles_cannot_change_settings(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    for persona in (tenant.builder, tenant.governor, tenant.owner, tenant.outsider):
        response = await client.patch("/settings", json={"legend": False}, headers=persona.headers)
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "forbidden"
    assert (await client.get("/settings", headers=tenant.admin.headers)).json()["legend"] is True


async def test_cookie_writes_need_the_csrf_token(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    member = await create_member(
        admin, org["id"], await group_ids(admin, org["id"], "Administrators")
    )
    browser, _ = await ready_member(browsers(), member)

    refused = await browser.client.patch(
        "/settings", json={"legend": False}, headers={"Origin": TEST_ORIGIN}
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "csrf_failed"
    reset_refused = await browser.client.post(
        "/appearance/reset", headers={"Origin": "https://evil.test", "X-CSRF-Token": browser.csrf}
    )
    assert reset_refused.status_code == 403 and reset_refused.json()["code"] == "csrf_failed"

    accepted = await browser.call("PATCH", "/settings", json={"legend": False})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["legend"] is False


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"companyMode": "single"},
        {"refresh": "2 h"},
        {"llmMonthlyTokenCap": -1},
        {"ocrMonthlyPageCap": 1_000_001},
        {"egressAllowlist": ["h" * 301]},
        {"voice": 3},
    ],
)
async def test_invalid_settings_bodies_are_refused(
    client: httpx.AsyncClient, tenant: TenantFixture, body: dict
) -> None:
    response = await client.patch("/settings", json=body, headers=tenant.admin.headers)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_failed"


@pytest.mark.parametrize("key", ["approvalRequired", "readOnlyConnectors"])
async def test_locked_settings_answer_locked_setting(
    client: httpx.AsyncClient, tenant: TenantFixture, key: str
) -> None:
    for value in (True, False):
        response = await client.patch("/settings", json={key: value}, headers=tenant.admin.headers)
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "locked_setting"


async def test_multi_company_stays_off_in_single_company_mode(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    tenant = await make_tenant()
    await organization_settings_repository.set_company_mode(
        session, tenant.tenant_id, CompanyMode.SINGLE
    )
    await session.commit()

    refused = await client.patch(
        "/settings", json={"multiCompany": True}, headers=tenant.admin.headers
    )

    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "locked_setting"
    read = await client.get("/settings", headers=tenant.admin.headers)
    assert read.json()["companyMode"] == "single"
    assert read.json()["multiCompany"] is False


async def test_a_change_in_one_tenant_leaves_the_other_untouched(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    a, b = await make_tenant(), await make_tenant()

    response = await client.patch(
        "/settings", json={"animations": False, "agentAccess": False}, headers=a.admin.headers
    )

    assert response.status_code == 200, response.text
    b_settings = await session.get(TenantSettings, b.tenant_id, populate_existing=True)
    assert b_settings is not None
    assert b_settings.animations is True and b_settings.agent_access is True
    assert (await client.get("/settings", headers=b.admin.headers)).json()["animations"] is True
    b_audit = await client.get("/audit", headers=b.admin.headers)
    assert all(e["what"] != "animations disabled" for e in b_audit.json()["items"])


async def test_cross_company_turns_off_at_once_when_nothing_crosses(
    client: httpx.AsyncClient,
) -> None:
    tenant = await make_tenant()

    off = await client.patch(
        "/settings", json={"crossCompany": False}, headers=tenant.admin.headers
    )

    assert off.status_code == 200, off.text
    assert off.json()["crossCompany"] is False
    on = await client.patch("/settings", json={"crossCompany": True}, headers=tenant.admin.headers)
    assert on.status_code == 200 and on.json()["crossCompany"] is True


async def test_cross_company_off_needs_confirmation_while_relations_cross(
    client: httpx.AsyncClient,
) -> None:
    tenant = await make_tenant()
    await cross_company_relation(client, tenant, approve=True)

    refused = await client.patch(
        "/settings", json={"crossCompany": False}, headers=tenant.admin.headers
    )

    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "confirmation_required"
    assert (await client.get("/settings", headers=tenant.admin.headers)).json()["crossCompany"]


async def test_cross_company_impact_lists_pairs_samples_and_pending(
    client: httpx.AsyncClient,
) -> None:
    tenant = await make_tenant()
    await cross_company_relation(client, tenant, approve=True)
    await cross_company_relation(client, tenant, approve=False)

    impact = await client.get("/settings/cross-company/impact", headers=tenant.admin.headers)

    assert impact.status_code == 200, impact.text
    body = impact.json()
    assert body["relations"] == 1
    assert body["pendingProposals"] == 1
    assert len(body["pairs"]) == 1 and body["pairs"][0]["count"] == 1
    assert body["pairs"][0]["companyA"] == tenant.company_name
    assert len(body["samples"]) == 1 and " buys from " in body["samples"][0]
    refused = await client.get("/settings/cross-company/impact", headers=tenant.governor.headers)
    assert refused.status_code == 403


async def test_disable_needs_the_typed_word(
    client: httpx.AsyncClient, tenant: TenantFixture
) -> None:
    mismatch = await client.post(
        "/settings/cross-company/disable",
        json={"confirmation": "DISABLE"},
        headers=tenant.admin.headers,
    )
    forbidden = await client.post(
        "/settings/cross-company/disable",
        json={"confirmation": "disable"},
        headers=tenant.governor.headers,
    )
    invalid = await client.post(
        "/settings/cross-company/disable", json={}, headers=tenant.admin.headers
    )

    assert mismatch.status_code == 409 and mismatch.json()["code"] == "confirmation_mismatch"
    assert forbidden.status_code == 403
    assert invalid.status_code == 422


async def test_disable_is_refused_once_companies_no_longer_interact(
    client: httpx.AsyncClient,
) -> None:
    tenant = await make_tenant()
    off = await client.patch(
        "/settings", json={"crossCompany": False}, headers=tenant.admin.headers
    )
    assert off.status_code == 200, off.text

    again = await client.post(
        "/settings/cross-company/disable",
        json={"confirmation": "disable"},
        headers=tenant.admin.headers,
    )

    assert again.status_code == 409, again.text
    assert again.json()["code"] == "cross_company_disabled"
    open_changes = await client.get("/proposals?pageSize=200", headers=tenant.admin.headers)
    assert all(p["type"] != "change" for p in open_changes.json()["items"])


async def test_disable_removes_relations_rejects_proposals_and_is_one_approved_change(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    tenant = await make_tenant()
    approved_relation = await cross_company_relation(client, tenant, approve=True)
    pending = await cross_company_relation(client, tenant, approve=False)

    response = await client.post(
        "/settings/cross-company/disable",
        json={"confirmation": "disable"},
        headers=tenant.admin.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["removedRelations"] == 1
    assert body["rejectedProposals"] == 1
    assert body["settings"]["crossCompany"] is False
    assert body["proposal"]["type"] == "change"
    assert body["proposal"]["changeKind"] == "remove_cross_company_links"
    assert body["proposal"]["state"] == "approved"
    assert body["proposal"]["bulk"] is True
    assert body["proposal"]["companyId"] is None
    assert body["proposal"]["approvals"][0]["userId"] == str(tenant.admin.user_id)
    assert body["audit"]["kind"] == "setting"
    assert body["audit"]["what"] == (
        "companies may interact disabled · 1 cross-company relationship removed"
    )
    assert body["audit"]["proposalId"] == body["proposal"]["id"]

    scene = (await client.get("/scene", headers=tenant.governor.headers)).json()
    assert approved_relation["relationId"] not in [link["id"] for link in scene["links"]]
    assert scene["settings"]["crossCompany"] is False
    rejected = await client.get(f"/proposals/{pending['id']}", headers=tenant.governor.headers)
    assert rejected.json()["state"] == "rejected"
    stored = await client.get(
        f"/proposals/{body['proposal']['id']}", headers=tenant.governor.headers
    )
    assert stored.status_code == 200 and stored.json()["state"] == "approved"
    assert body["audit"]["what"] in await audit_texts(client, tenant)

    # Companies no longer interact: a new cross-company relation is refused.
    other = await add_company(client, tenant, "Third")
    home = await approved(client, tenant, "Supplier", domain_key="supply")
    foreign = await foreign_concept(client, tenant, other)
    again = await client.post(
        "/relations",
        json={"type": "relation", "aId": home["id"], "bId": foreign["id"], "action": "supplies"},
        headers=tenant.builder.headers,
    )
    assert again.status_code == 409 and again.json()["code"] == "cross_company_disabled"
