"""A super admin enters an organization and acts inside it with every tenant role: the entry is
super admin only and CSRF-protected, everything a tenant Administrator, Builder, Governor or
Auditor can do works, the separation of approvers still holds, row-level security confines the
acting session to that one organization, every action is audited in the organization's log as
the super admin, and exit, sign-out and expiry clear the access."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx

from app.main import API_PREFIX
from tests.auth_helpers import (
    create_member,
    create_organization,
    group_ids,
    platform_execute,
    platform_rows,
    ready_member,
    signed_in,
)
from tests.conftest import AccountFixture, Browser, TenantFixture, make_tenant
from tests.test_tenant_isolation import (
    OrganizationB,
    b_bodies,
    b_path,
    b_snapshot,
    organization_b,  # noqa: F401
    organization_routes,
)

ENTERED_WHAT = "Entered the organization as platform super admin, with every role"


async def entered(browser: Browser, tenant_id: uuid.UUID) -> dict[str, Any]:
    response = await browser.call("POST", f"/admin/organizations/{tenant_id}/enter")
    assert response.status_code == 200, response.text
    return response.json()


def company_body(name: str) -> dict[str, Any]:
    return {"name": f"{name} {uuid.uuid4().hex[:6]}", "sub": "one line", "start": "one_cell"}


def concept_body(tenant: TenantFixture, label: str) -> dict[str, Any]:
    return {
        "type": "concept",
        "companyId": str(tenant.company_id),
        "parentId": str(tenant.root_id),
        "label": label,
        "domainKey": "production",
        "action": "operates",
    }


async def organization_log(tenant_id: uuid.UUID) -> list[Any]:
    return await platform_rows(
        "SELECT kind, actor_kind::text, actor_account_id, what FROM ontaix.audit_entry"
        " WHERE tenant_id = :t ORDER BY id",
        t=tenant_id,
    )


async def platform_actions(account_id: uuid.UUID, tenant_id: uuid.UUID) -> list[str]:
    rows = await platform_rows(
        "SELECT action FROM ontaix.platform_audit_entry"
        " WHERE actor_account_id = :a AND target_tenant_id = :t ORDER BY id",
        a=account_id,
        t=tenant_id,
    )
    return [r[0] for r in rows]


async def test_only_a_super_admin_enters_an_organization(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    other = await create_organization(admin)
    member = await create_member(
        admin, org["id"], await group_ids(admin, org["id"], "Administrators")
    )
    browser, _ = await ready_member(browsers(), member)

    for target in (org["id"], other["id"]):
        response = await browser.call("POST", f"/admin/organizations/{target}/enter")
        assert response.status_code == 403, response.text
    assert (await browser.call("POST", "/admin/exit")).status_code == 403
    assert (await browser.call("GET", "/admin/organizations")).status_code == 403

    anonymous = await browsers().call("POST", f"/admin/organizations/{org['id']}/enter")
    assert anonymous.status_code == 401


async def test_entering_needs_the_csrf_token_and_an_enabled_organization(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)

    forged = await admin.call(
        "POST",
        f"/admin/organizations/{org['id']}/enter",
        headers={"X-CSRF-Token": "x" * 43},
    )
    assert forged.status_code == 403 and forged.json()["code"] == "csrf_failed"
    assert (await admin.call("GET", "/auth/session")).json()["acting"] is None

    unknown = await admin.call("POST", f"/admin/organizations/{uuid.uuid4()}/enter")
    assert unknown.status_code == 404
    off = await admin.call("POST", f"/admin/organizations/{org['id']}/disable")
    assert off.status_code == 200
    disabled = await admin.call("POST", f"/admin/organizations/{org['id']}/enter")
    assert disabled.status_code == 409 and disabled.json()["code"] == "organization_disabled"


async def test_inside_the_organization_the_super_admin_does_everything_and_is_audited(
    browsers: Callable[[], Browser],
    super_admin: AccountFixture,
    client: httpx.AsyncClient,
) -> None:
    tenant = await make_tenant()
    admin = await signed_in(browsers(), super_admin)
    assert (await admin.call("GET", "/scene")).status_code == 403
    before = admin.cookie()

    session = await entered(admin, tenant.tenant_id)

    assert admin.cookie() != before
    assert session["kind"] == "platform"
    assert session["acting"]["organization"]["id"] == str(tenant.tenant_id)
    assert session["acting"]["organization"]["name"] == f"Tenant {tenant.slug}"
    assert session["support"] is None
    scene = await admin.call("GET", "/scene")
    assert scene.status_code == 200, scene.text
    assert [c["name"] for c in scene.json()["companies"]] == [tenant.company_name]

    # Administrator: companies, settings and the audit log.
    company = await admin.call("POST", "/companies", json=company_body("Entered Co"))
    assert company.status_code == 201, company.text
    assert (await admin.call("GET", "/audit")).status_code == 200
    assert (await admin.call("GET", "/cost")).status_code == 200
    # Builder: a proposal. Governor: its approval.
    proposed = await admin.call("POST", "/concepts", json=concept_body(tenant, "Boiler"))
    assert proposed.status_code == 202, proposed.text
    approved = await admin.call("POST", f"/proposals/{proposed.json()['id']}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["proposal"]["state"] == "approved"
    # Export of the approved model.
    exported = await admin.call(
        "GET",
        "/export",
        params={"scope": "company", "format": "turtle", "companyId": str(tenant.company_id)},
    )
    assert exported.status_code == 200, exported.text
    assert "Boiler" in exported.text

    log = await organization_log(tenant.tenant_id)
    entry = next(e for e in log if e[0] == "platform" and e[3] == ENTERED_WHAT)
    assert entry[1] == "platform" and entry[2] == super_admin.account_id
    actions = [e for e in log if e[0] in ("company", "concept")]
    assert actions and all(e[1] == "user" and e[2] == super_admin.account_id for e in actions), (
        actions
    )

    # The organization's own Administrator reads those entries with the platform marker.
    seen = await client.get("/audit", headers=tenant.admin.headers)
    assert seen.status_code == 200
    items = seen.json()["items"]
    concept_entries = [i for i in items if i["kind"] == "concept"]
    assert concept_entries
    assert all(
        i["actor"]["kind"] == "user"
        and i["actor"]["platformAccountId"] == str(super_admin.account_id)
        and i["actor"]["name"]
        for i in concept_entries
    ), concept_entries
    platform_entries = [i for i in items if i["kind"] == "platform"]
    assert any(i["what"] == ENTERED_WHAT for i in platform_entries)
    assert all(i["actor"]["kind"] == "platform" for i in platform_entries)

    left = await admin.call("POST", "/admin/exit")
    assert left.status_code == 200, left.text
    assert left.json()["acting"] is None
    assert (await admin.call("GET", "/scene")).status_code == 403
    assert (await admin.call("GET", "/admin/organizations")).status_code == 200
    assert await platform_actions(super_admin.account_id, tenant.tenant_id) == [
        "organization_entered",
        "organization_exited",
    ]
    log = await organization_log(tenant.tenant_id)
    assert log[-1][0] == "platform" and log[-1][2] == super_admin.account_id
    assert "Left the organization" in log[-1][3]
    # Leaving again changes nothing and answers the session as it is.
    again = await admin.call("POST", "/admin/exit")
    assert again.status_code == 200 and again.json()["acting"] is None
    assert await platform_actions(super_admin.account_id, tenant.tenant_id) == [
        "organization_entered",
        "organization_exited",
    ]


async def test_the_separation_of_approvers_still_holds_inside(
    browsers: Callable[[], Browser], super_admin: AccountFixture, client: httpx.AsyncClient
) -> None:
    tenant = await make_tenant()
    await platform_execute(
        "UPDATE ontaix.tenant_settings SET two_approvers = true WHERE tenant_id = :t",
        t=tenant.tenant_id,
    )
    admin = await signed_in(browsers(), super_admin)
    await entered(admin, tenant.tenant_id)
    created = (await admin.call("POST", "/concepts", json=concept_body(tenant, "Invoice"))).json()
    assert (await admin.call("POST", f"/proposals/{created['id']}/approve")).status_code == 200
    rename = await admin.call("PATCH", f"/concepts/{created['conceptId']}", json={"label": "Bill"})
    assert rename.status_code == 202, rename.text
    change_id = rename.json()["id"]
    first = await admin.call("POST", f"/proposals/{change_id}/approve")
    assert first.status_code == 200 and first.json()["proposal"]["state"] == "half_approved"

    same = await admin.call("POST", f"/proposals/{change_id}/second-approve")

    assert same.status_code == 409 and same.json()["code"] == "same_approver"
    other = await client.post(
        f"/proposals/{change_id}/second-approve", headers=tenant.governor.headers
    )
    assert other.status_code == 200 and other.json()["proposal"]["state"] == "approved"


async def test_while_acting_in_a_nothing_of_b_is_readable_or_writable(
    browsers: Callable[[], Browser],
    super_admin: AccountFixture,
    organization_b: OrganizationB,  # noqa: F811
) -> None:
    a = await make_tenant()
    admin = await signed_in(browsers(), super_admin)
    await entered(admin, a.tenant_id)
    before = await b_snapshot(organization_b)

    reads = writes = 0
    for route in organization_routes():
        path = route.path[len(API_PREFIX) :]
        if "GET" in route.methods:
            if "{" in route.path:
                response = await admin.call("GET", b_path(route, organization_b))
                assert response.status_code in (403, 404, 410), (route.path, response.text)
                markers = organization_b.markers[4:]
            else:
                response = await admin.call("GET", path)
                assert response.status_code < 500, (route.path, response.text)
                markers = organization_b.markers
            reads += 1
            for marker in markers:
                assert marker not in response.text, (route.path, marker)
        for method in route.methods - {"GET", "HEAD"}:
            for body in b_bodies(organization_b):
                response = await admin.call(method, b_path(route, organization_b), json=body)
                writes += 1
                assert response.status_code < 500 or response.status_code == 503, (
                    method,
                    route.path,
                    response.text,
                )
                for marker in organization_b.markers[4:]:
                    assert marker not in response.text, (method, route.path, marker)
    assert reads >= 14 and writes >= 100
    assert await b_snapshot(organization_b) == before
    # The sweep's writes landed in A (a company among them), never in B.
    scene = (await admin.call("GET", "/scene")).json()
    company_ids = [c["id"] for c in scene["companies"]]
    assert str(a.company_id) in company_ids
    assert str(organization_b.tenant.company_id) not in company_ids
    assert (await admin.call("GET", f"/proposals/{organization_b.proposal_id}")).status_code == 404


async def test_entering_another_organization_or_a_support_session_moves_the_access(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    first, second = await make_tenant(), await make_tenant()
    admin = await signed_in(browsers(), super_admin)
    support = await admin.call(
        "POST", f"/admin/organizations/{first.tenant_id}/support-session", json={"reason": "Look"}
    )
    assert support.status_code == 200 and support.json()["support"] is not None

    session = await entered(admin, first.tenant_id)

    assert session["support"] is None
    assert session["acting"]["organization"]["id"] == str(first.tenant_id)
    added = await admin.call("POST", "/companies", json=company_body("Writable"))
    assert added.status_code == 201, added.text
    assert await platform_actions(super_admin.account_id, first.tenant_id) == [
        "support_session_started",
        "support_session_ended",
        "organization_entered",
    ]

    moved = await entered(admin, second.tenant_id)

    assert moved["acting"]["organization"]["id"] == str(second.tenant_id)
    scene = (await admin.call("GET", "/scene")).json()
    assert [c["name"] for c in scene["companies"]] == [second.company_name]
    assert (await platform_actions(super_admin.account_id, first.tenant_id))[-1] == (
        "organization_exited"
    )
    assert await platform_actions(super_admin.account_id, second.tenant_id) == [
        "organization_entered"
    ]

    back = await admin.call(
        "POST", f"/admin/organizations/{first.tenant_id}/support-session", json={"reason": "Look"}
    )
    assert back.status_code == 200
    assert back.json()["acting"] is None and back.json()["support"] is not None
    refused = await admin.call("POST", "/companies", json=company_body("Read only"))
    assert refused.status_code == 403, refused.text
    assert await platform_actions(super_admin.account_id, second.tenant_id) == [
        "organization_entered",
        "organization_exited",
    ]


async def test_sign_out_and_expiry_clear_the_access(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    tenant = await make_tenant()
    admin = await signed_in(browsers(), super_admin)
    await entered(admin, tenant.tenant_id)

    assert (await admin.call("POST", "/auth/sign-out")).status_code == 204
    await signed_in(admin, super_admin)
    assert (await admin.call("GET", "/auth/session")).json()["acting"] is None
    assert (await admin.call("GET", "/scene")).status_code == 403
    assert await platform_actions(super_admin.account_id, tenant.tenant_id) == [
        "organization_entered",
        "organization_exited",
    ]
    log = await organization_log(tenant.tenant_id)
    assert log[-1][0] == "platform" and "signed out" in log[-1][3]

    await entered(admin, tenant.tenant_id)
    await platform_execute(
        "UPDATE ontaix.auth_session SET idle_expires_at = now() - interval '1 second'"
        " WHERE token_hash = sha256(convert_to(:t, 'UTF8'))",
        t=admin.cookie(),
    )
    assert (await admin.call("GET", "/scene")).status_code == 401
    assert (await admin.call("GET", "/auth/session")).status_code == 401
    await signed_in(admin, super_admin)
    assert (await admin.call("GET", "/auth/session")).json()["acting"] is None
    assert (await admin.call("GET", "/scene")).status_code == 403
    assert await platform_actions(super_admin.account_id, tenant.tenant_id) == [
        "organization_entered",
        "organization_exited",
        "organization_entered",
        "organization_exited",
    ]
    log = await organization_log(tenant.tenant_id)
    assert log[-1][0] == "platform" and "expired" in log[-1][3]


async def test_disabling_the_organization_ends_the_access(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    tenant = await make_tenant()
    admin = await signed_in(browsers(), super_admin)
    await entered(admin, tenant.tenant_id)

    disabled = await admin.call("POST", f"/admin/organizations/{tenant.tenant_id}/disable")

    # The acting session ended with the organization's sessions; the super admin signs in again.
    assert disabled.status_code == 200, disabled.text
    assert (await admin.call("GET", "/auth/session")).status_code == 401
    await signed_in(admin, super_admin)
    assert (await admin.call("GET", "/auth/session")).json()["acting"] is None
