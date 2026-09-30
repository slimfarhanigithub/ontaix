"""The platform portal: organizations, their accounts, company mode, the super admin against an
organization's Administrator, and read-only support sessions."""

from __future__ import annotations

from collections.abc import Callable

from app.services import auth_upkeep_service
from tests.auth_helpers import (
    create_member,
    create_organization,
    group_ids,
    platform_execute,
    platform_rows,
    ready_member,
    signed_in,
)
from tests.conftest import AccountFixture, Browser, TenantFixture, generated_password

STARTER_GROUPS = {
    "Administrators": "administrator",
    "Governors": "governor",
    "Builders": "builder",
    "Members": "member",
    "Auditors": "auditor",
}


async def test_a_new_organization_has_five_starter_groups_and_nothing_else(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin, company_mode="single")

    assert org["status"] == "active" and org["companyMode"] == "single"
    assert org["companies"] == 0 and org["users"] == 0
    groups = (await admin.call("GET", f"/admin/organizations/{org['id']}/groups")).json()
    assert {g["name"]: [r["role"] for r in g["roles"]] for g in groups} == {
        name: [role] for name, role in STARTER_GROUPS.items()
    }
    assert all(r["scope"]["kind"] == "tenant" for g in groups for r in g["roles"])
    audit = await platform_rows(
        "SELECT action FROM ontaix.platform_audit_entry WHERE target_tenant_id = :t",
        t=org["id"],
    )
    assert audit == [("organization_created",)]


async def test_organization_names_are_unique_and_renames_are_audited_in_both_logs(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    other = await create_organization(admin)

    duplicate = await admin.call(
        "POST", "/admin/organizations", json={"name": org["name"].upper(), "companyMode": "single"}
    )
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "duplicate_organization"
    clash = await admin.call(
        "PATCH", f"/admin/organizations/{other['id']}", json={"name": org["name"]}
    )
    assert clash.status_code == 409
    renamed = await admin.call(
        "PATCH", f"/admin/organizations/{org['id']}", json={"name": org["name"] + " Renamed"}
    )
    assert renamed.status_code == 200 and renamed.json()["slug"] == org["slug"]
    copies = await platform_rows(
        "SELECT kind, actor_kind::text, actor_account_id FROM ontaix.audit_entry"
        " WHERE tenant_id = :t",
        t=org["id"],
    )
    assert copies == [("platform", "platform", super_admin.account_id)]
    listing = (await admin.call("GET", "/admin/organizations?q=Renamed&pageSize=200")).json()
    assert [o["id"] for o in listing["items"]] == [org["id"]]


async def test_company_mode_caps_the_organization_at_one_company(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin, company_mode="single")
    member = await create_member(
        admin, org["id"], await group_ids(admin, org["id"], "Administrators")
    )
    browser, _ = await ready_member(browsers(), member)

    first = await browser.call(
        "POST", "/companies", json={"name": "Only Co", "sub": "one line", "start": "one_cell"}
    )
    assert first.status_code == 201, first.text
    second = await browser.call(
        "POST", "/companies", json={"name": "Second Co", "sub": "line", "start": "one_cell"}
    )
    assert second.status_code == 409 and second.json()["code"] == "company_limit"
    scene = (await browser.call("GET", "/scene")).json()
    assert scene["settings"]["companyMode"] == "single"
    assert scene["settings"]["multiCompany"] is False

    multiple = await admin.call(
        "PATCH", f"/admin/organizations/{org['id']}", json={"companyMode": "multiple"}
    )
    assert multiple.status_code == 200
    assert (
        await browser.call(
            "POST", "/companies", json={"name": "Second Co", "sub": "line", "start": "one_cell"}
        )
    ).status_code == 201
    refused = await admin.call(
        "PATCH", f"/admin/organizations/{org['id']}", json={"companyMode": "single"}
    )
    assert refused.status_code == 409 and refused.json()["code"] == "company_limit"
    events = await platform_rows(
        "SELECT payload->'changed' FROM ontaix.outbox WHERE tenant_id = :t"
        " AND aggregate = 'settings' AND actor_kind = 'platform'",
        t=org["id"],
    )
    assert events and ["companyMode"] in [e[0] for e in events]


async def test_disabling_an_organization_ends_its_sessions_and_keeps_its_data(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    member = await create_member(admin, org["id"], await group_ids(admin, org["id"], "Members"))
    browser, member = await ready_member(browsers(), member)

    disabled = await admin.call("POST", f"/admin/organizations/{org['id']}/disable")
    assert disabled.json()["status"] == "disabled"
    assert (await browser.call("GET", "/scene")).status_code == 401
    assert (await browsers().sign_in(member.email, member.password)).status_code == 401
    add = await admin.call(
        "POST",
        f"/admin/organizations/{org['id']}/users",
        json={
            "email": "late@org.test",
            "name": "Late",
            "password": generated_password(),
            "groupIds": [],
        },
    )
    assert add.status_code == 409 and add.json()["code"] == "organization_disabled"

    enabled = await admin.call("POST", f"/admin/organizations/{org['id']}/enable")
    assert enabled.json()["status"] == "active"
    assert (await browsers().sign_in(member.email, member.password)).status_code == 200


async def test_accounts_created_edited_disabled_and_reset_by_the_super_admin(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    builders, members = await group_ids(admin, org["id"], "Builders", "Members")
    member = await create_member(admin, org["id"], [builders])
    base = f"/admin/organizations/{org['id']}/users"

    duplicate = await admin.call(
        "POST",
        base,
        json={
            "email": member.email.upper(),
            "name": "Twin",
            "password": generated_password(),
            "groupIds": [],
        },
    )
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "duplicate_email"
    foreign_org = await create_organization(admin)
    foreign = await group_ids(admin, foreign_org["id"], "Builders")
    refused = await admin.call(
        "POST",
        base,
        json={
            "email": "f@org.test",
            "name": "F",
            "password": generated_password(),
            "groupIds": foreign,
        },
    )
    assert refused.status_code == 422
    weak = await admin.call(
        "POST",
        base,
        json={"email": "w@org.test", "name": "W", "password": "qwerty123456", "groupIds": []},
    )
    assert weak.status_code == 422 and weak.json()["code"] == "password_rejected"

    listed = (await admin.call("GET", f"{base}?filter[status]=mustChangePassword")).json()
    assert [u["email"] for u in listed["items"]] == [member.email]
    assert "password" not in str(listed).lower().replace("mustchangepassword", "")

    edited = await admin.call(
        "PATCH", f"{base}/{member.user_id}", json={"name": "Renamed", "groupIds": [members]}
    )
    assert edited.status_code == 200
    assert [g["name"] for g in edited.json()["groups"]] == ["Members"]
    group_audit = await platform_rows(
        "SELECT what FROM ontaix.audit_entry WHERE tenant_id = :t AND kind = 'groups' ORDER BY id",
        t=org["id"],
    )
    assert len(group_audit) == 3

    browser, member = await ready_member(browsers(), member)
    await admin.call("POST", f"{base}/{member.user_id}/disable")
    assert (await browser.call("GET", "/auth/session")).status_code == 401
    assert (await browsers().sign_in(member.email, member.password)).status_code == 401
    await admin.call("POST", f"{base}/{member.user_id}/enable")

    browser = await signed_in(browsers(), member)
    for _ in range(5):
        await browsers().sign_in(member.email, generated_password())
    assert (await admin.call("GET", f"{base}/{member.user_id}")).json()["locked"] is True
    reset_to = generated_password()
    reset = await admin.call(
        "PUT", f"{base}/{member.user_id}/password", json={"newPassword": reset_to}
    )
    assert reset.status_code == 204
    assert (await browser.call("GET", "/auth/session")).status_code == 401
    after = await browsers().sign_in(member.email, reset_to)
    assert after.status_code == 200 and after.json()["mustChangePassword"] is True
    actions = await platform_rows(
        "SELECT action FROM ontaix.platform_audit_entry WHERE target_account_id = :a"
        " AND actor_account_id = :s ORDER BY id",
        a=member.account_id,
        s=super_admin.account_id,
    )
    assert [a[0] for a in actions] == [
        "account_created",
        "account_updated",
        "account_disabled",
        "account_enabled",
        "password_reset",
    ]


async def test_an_organization_administrator_cannot_reach_the_platform(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    member = await create_member(
        admin, org["id"], await group_ids(admin, org["id"], "Administrators")
    )
    browser, _ = await ready_member(browsers(), member)

    for method, path in (
        ("GET", "/admin/organizations"),
        ("POST", "/admin/organizations"),
        ("GET", f"/admin/organizations/{org['id']}/users"),
        ("PUT", f"/admin/organizations/{org['id']}/users/{member.user_id}/password"),
        ("GET", "/admin/audit"),
        ("POST", f"/admin/organizations/{org['id']}/support-session"),
    ):
        response = await browser.call(method, path, json={})
        assert response.status_code == 403, (path, response.text)


async def test_the_super_admin_sees_no_organization_without_a_support_session(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)

    for path in ("/scene", "/companies", "/audit", "/proposals"):
        response = await admin.call("GET", path)
        assert response.status_code == 403, (path, response.text)


async def test_a_support_session_is_read_only_audited_and_ends(
    browsers: Callable[[], Browser], super_admin: AccountFixture, tenant: TenantFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    before = admin.cookie()
    path = f"/admin/organizations/{tenant.tenant_id}/support-session"
    assert (await admin.call("POST", path, json={"reason": ""})).status_code == 422

    started = await admin.call("POST", path, json={"reason": "Customer ticket 42"})

    assert started.status_code == 200, started.text
    assert admin.cookie() != before
    support = started.json()["support"]
    assert support["organization"]["id"] == str(tenant.tenant_id)
    assert support["reason"] == "Customer ticket 42"
    scene = await admin.call("GET", "/scene")
    assert scene.status_code == 200
    assert [c["name"] for c in scene.json()["companies"]] == [tenant.company_name]
    assert (await admin.call("GET", "/audit")).status_code == 200
    for method, target in (
        ("POST", "/companies"),
        ("POST", "/proposals/approve-all"),
        ("POST", "/teach/parse"),
    ):
        response = await admin.call(method, target, json={"name": "X", "sub": "Y"})
        assert response.status_code == 403, (target, response.text)
    copies = await platform_rows(
        "SELECT kind, actor_kind::text, what FROM ontaix.audit_entry"
        " WHERE tenant_id = :t AND kind = 'platform' ORDER BY id",
        t=tenant.tenant_id,
    )
    assert copies and copies[-1][1] == "platform" and "Customer ticket 42" in copies[-1][2]

    ended = await admin.call("DELETE", "/admin/support-session")
    assert ended.status_code == 200 and ended.json()["support"] is None
    assert (await admin.call("GET", "/scene")).status_code == 403
    actions = await platform_rows(
        "SELECT action FROM ontaix.platform_audit_entry WHERE actor_account_id = :a"
        " AND target_tenant_id = :t ORDER BY id",
        a=super_admin.account_id,
        t=tenant.tenant_id,
    )
    assert [a[0] for a in actions] == ["support_session_started", "support_session_ended"]


async def test_a_support_session_expires_after_its_hour(
    browsers: Callable[[], Browser], super_admin: AccountFixture, tenant: TenantFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    started = await admin.call(
        "POST",
        f"/admin/organizations/{tenant.tenant_id}/support-session",
        json={"reason": "Checking a report"},
    )
    until = started.json()["support"]["until"]
    assert until <= started.json()["absoluteExpiresAt"]
    await platform_execute(
        "UPDATE ontaix.auth_session SET support_until = now() - interval '1 second'"
        " WHERE token_hash = sha256(convert_to(:t, 'UTF8'))",
        t=admin.cookie(),
    )

    assert (await admin.call("GET", "/scene")).status_code == 403
    await auth_upkeep_service.run_once()

    session = (await admin.call("GET", "/auth/session")).json()
    assert session["support"] is None
    ended = await platform_rows(
        "SELECT actor_account_id FROM ontaix.platform_audit_entry"
        " WHERE action = 'support_session_ended' AND target_account_id = :a",
        a=super_admin.account_id,
    )
    assert ended == [(None,)]


async def test_the_platform_audit_log_filters(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)

    page = await admin.call(
        "GET", f"/admin/audit?filter[organizationId]={org['id']}&filter[ok]=true"
    )

    assert page.status_code == 200, page.text
    items = page.json()["items"]
    assert [i["action"] for i in items] == ["organization_created"]
    assert items[0]["actor"]["email"] == super_admin.email
    assert items[0]["organization"]["id"] == org["id"]
    assert (await admin.call("GET", "/admin/audit?filter[nope]=1")).status_code == 400
