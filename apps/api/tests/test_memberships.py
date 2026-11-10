"""An account belongs to several organizations through memberships: sign-in with none, one or
several of them, the choice and switch of an organization, removal and re-adding with the same
directory user, disabling per membership, the refusals of Add existing account, and the
isolation of the two organizations of one person."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from tests.auth_helpers import (
    Member,
    change_password,
    create_member,
    create_organization,
    group_ids,
    platform_rows,
    ready_member,
    signed_in,
)
from tests.conftest import TEST_ORIGIN, AccountFixture, Browser, generated_password


async def add_existing(
    admin: Browser, organization_id: str, email: str, groups: list[str] | None = None
) -> Any:
    return await admin.call(
        "POST",
        f"/admin/organizations/{organization_id}/memberships",
        json={"email": email, "groupIds": groups or []},
    )


async def member_of_two(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> tuple[Browser, Member, dict[str, Any], dict[str, Any]]:
    """The super admin's browser and a member of organizations A and B (Members of each), with
    the member's directory user of B under `b["userId"]`."""
    admin = await signed_in(browsers(), super_admin)
    a, b = await create_organization(admin), await create_organization(admin)
    member = await create_member(admin, a["id"], await group_ids(admin, a["id"], "Members"))
    added = await add_existing(
        admin, b["id"], member.email, await group_ids(admin, b["id"], "Members")
    )
    assert added.status_code == 201, added.text
    return admin, member, a, {**b, "userId": added.json()["id"]}


async def choose(browser: Browser, organization_id: str) -> Any:
    return await browser.call(
        "PUT", "/auth/session/organization", json={"organizationId": organization_id}
    )


async def test_one_membership_enters_the_organization_directly(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    member = await create_member(admin, org["id"], await group_ids(admin, org["id"], "Members"))

    browser, _ = await ready_member(browsers(), member)

    session = (await browser.call("GET", "/auth/session")).json()
    assert session["kind"] == "member"
    assert session["organization"]["id"] == org["id"]
    assert [o["id"] for o in session["organizations"]] == [org["id"]]
    assert session["userId"] == str(member.user_id)
    assert (await browser.call("GET", "/scene")).status_code == 200
    subject = await platform_rows(
        "SELECT issuer, subject FROM ontaix.app_user WHERE id = :u", u=member.user_id
    )
    assert subject == [("local", f"{member.account_id}:{org['id']}")]


async def test_no_membership_is_refused_after_the_password_check(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    member = await create_member(admin, org["id"])
    removed = await admin.call("DELETE", f"/admin/organizations/{org['id']}/users/{member.user_id}")
    assert removed.status_code == 204, removed.text

    wrong = await browsers().sign_in(member.email, generated_password())
    assert wrong.status_code == 401 and wrong.json()["code"] == "invalid_credentials"
    refused = await browsers().sign_in(member.email, member.password)

    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "no_organization"
    assert refused.json()["detail"] == (
        "Your account belongs to no organization. Ask your administrator."
    )
    assert refused.headers.get("set-cookie") is None
    audited = await platform_rows(
        "SELECT action, ok, what FROM ontaix.platform_audit_entry WHERE actor_account_id = :a"
        " ORDER BY id DESC LIMIT 1",
        a=member.account_id,
    )
    assert audited == [("sign_in_failed", False, "Sign-in refused: no organization")]
    # The refusal with the right password is no failed attempt: four more wrong ones do not lock.
    for _ in range(3):
        assert (await browsers().sign_in(member.email, generated_password())).status_code == 401
    assert (await browsers().sign_in(member.email, member.password)).status_code == 403


async def test_several_memberships_ask_for_a_choice_then_enter_the_chosen_one(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin, member, a, b = await member_of_two(browsers, super_admin)
    browser = browsers()
    first = await browser.sign_in(member.email, member.password)
    assert first.status_code == 200, first.text
    assert first.json()["mustChangePassword"] is True and first.json()["organization"] is None
    # The forced password change comes first.
    early = await choose(browser, a["id"])
    assert early.status_code == 403 and early.json()["code"] == "password_change_required"
    member = await change_password(browser, member)

    session = (await browser.call("GET", "/auth/session")).json()
    assert session["organization"] is None and session["userId"] is None
    assert {o["id"] for o in session["organizations"]} == {a["id"], b["id"]}
    assert [o["name"] for o in session["organizations"]] == sorted(
        [a["name"], b["name"]], key=str.lower
    )
    for path in ("/scene", "/companies", "/proposals"):
        response = await browser.call("GET", path)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["code"] == "organization_not_chosen"
    before = browser.cookie()

    chosen = await choose(browser, b["id"])

    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["organization"]["id"] == b["id"]
    assert len(chosen.json()["organizations"]) == 2
    assert browser.cookie() != before
    assert (await browser.call("GET", "/scene")).status_code == 200
    users_b = await platform_rows(
        "SELECT user_id FROM ontaix.account_membership WHERE account_id = :a AND tenant_id = :t",
        a=member.account_id,
        t=b["id"],
    )
    assert chosen.json()["userId"] == str(users_b[0][0])
    replay = await browsers().client.get(
        "/auth/session", headers={"Cookie": f"__Host-ontaix_session={before}"}
    )
    assert replay.status_code == 401
    rows = await platform_rows(
        "SELECT action, target_tenant_id FROM ontaix.platform_audit_entry"
        " WHERE actor_account_id = :a AND action = 'organization_chosen'",
        a=member.account_id,
    )
    assert rows == [("organization_chosen", uuid.UUID(b["id"]))]
    copies = await platform_rows(
        "SELECT kind, actor_kind::text, actor_user_id, what FROM ontaix.audit_entry"
        " WHERE tenant_id = :t AND what LIKE 'Entered %' ORDER BY id",
        t=b["id"],
    )
    assert copies == [("auth", "user", users_b[0][0], f"Entered {b['name']}")]


async def test_choosing_refuses_a_foreign_organization_a_forged_request_and_a_platform_account(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin, member, a, b = await member_of_two(browsers, super_admin)
    other = await create_organization(admin)
    browser, _ = await ready_member(browsers(), member)

    foreign = await choose(browser, other["id"])
    assert foreign.status_code == 403 and foreign.json()["code"] == "forbidden"
    unknown = await choose(browser, str(uuid.uuid4()))
    assert unknown.status_code == 403
    forged = await browser.client.put(
        "/auth/session/organization",
        json={"organizationId": a["id"]},
        headers={"Origin": TEST_ORIGIN},
    )
    assert forged.status_code == 403 and forged.json()["code"] == "csrf_failed"
    assert (await browser.call("GET", "/auth/session")).json()["organization"] is None
    platform = await choose(admin, a["id"])
    assert platform.status_code == 403 and platform.json()["code"] == "forbidden"
    anonymous = await choose(browsers(), a["id"])
    assert anonymous.status_code == 401


async def test_switching_moves_the_session_to_the_other_organization(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin, member, a, b = await member_of_two(browsers, super_admin)
    admin_a, _ = await ready_member(
        browsers(),
        await create_member(admin, a["id"], await group_ids(admin, a["id"], "Administrators")),
    )
    company = await admin_a.call(
        "POST", "/companies", json={"name": "Only In A", "sub": "one line", "start": "one_cell"}
    )
    assert company.status_code == 201, company.text
    browser, _ = await ready_member(browsers(), member)
    assert (await choose(browser, a["id"])).status_code == 200
    scene = (await browser.call("GET", "/scene")).json()
    assert [c["name"] for c in scene["companies"]] == ["Only In A"]
    first = browser.cookie()

    switched = await choose(browser, b["id"])

    assert switched.status_code == 200 and switched.json()["organization"]["id"] == b["id"]
    assert browser.cookie() != first
    scene = (await browser.call("GET", "/scene")).json()
    assert scene["companies"] == []
    assert "Only In A" not in (await browser.call("GET", "/audit")).text
    logins = await platform_rows(
        "SELECT u.tenant_id FROM ontaix.app_user u JOIN ontaix.account_membership m"
        " ON m.user_id = u.id WHERE m.account_id = :a AND u.last_login_at IS NOT NULL",
        a=member.account_id,
    )
    assert {r[0] for r in logins} == {uuid.UUID(a["id"]), uuid.UUID(b["id"])}


async def test_removal_keeps_the_user_for_history_and_re_adding_gives_it_back(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    builders, members = await group_ids(admin, org["id"], "Builders", "Members")
    member = await create_member(admin, org["id"], [builders])
    base = f"/admin/organizations/{org['id']}"
    assert (await admin.call("GET", f"{base}")).json()["users"] == 1

    removed = await admin.call("DELETE", f"{base}/users/{member.user_id}")

    assert removed.status_code == 204, removed.text
    assert (await admin.call("GET", f"{base}/users/{member.user_id}")).status_code == 404
    assert (await admin.call("GET", f"{base}/users")).json()["items"] == []
    assert (await admin.call("GET", f"{base}")).json()["users"] == 0
    assert (await admin.call("DELETE", f"{base}/users/{member.user_id}")).status_code == 404
    assert (await admin.call("POST", f"{base}/users/{member.user_id}/disable")).status_code == 404
    kept = await platform_rows(
        "SELECT u.id, m.removed_at IS NOT NULL FROM ontaix.app_user u"
        " JOIN ontaix.account_membership m ON m.user_id = u.id WHERE u.id = :u",
        u=member.user_id,
    )
    assert kept == [(member.user_id, True)]
    groups = await platform_rows(
        "SELECT count(*) FROM ontaix.group_member WHERE user_id = :u", u=member.user_id
    )
    assert groups == [(0,)]

    again = await add_existing(admin, org["id"], member.email.upper(), [members])

    assert again.status_code == 201, again.text
    assert again.json()["id"] == str(member.user_id)
    assert again.json()["accountId"] == str(member.account_id)
    assert again.json()["status"] == "active"
    assert [g["name"] for g in again.json()["groups"]] == ["Members"]
    listed = (await admin.call("GET", f"{base}/users")).json()["items"]
    assert [u["id"] for u in listed] == [str(member.user_id)]
    assert (await admin.call("GET", f"{base}")).json()["users"] == 1
    browser, _ = await ready_member(browsers(), member)
    assert (await browser.call("GET", "/scene")).status_code == 200
    actions = await platform_rows(
        "SELECT action FROM ontaix.platform_audit_entry WHERE target_account_id = :a"
        " AND actor_account_id = :s ORDER BY id",
        a=member.account_id,
        s=super_admin.account_id,
    )
    assert [a[0] for a in actions] == ["account_created", "membership_removed", "membership_added"]
    copies = await platform_rows(
        "SELECT actor_kind::text, actor_account_id, what FROM ontaix.audit_entry"
        " WHERE tenant_id = :t AND kind = 'platform' ORDER BY id",
        t=org["id"],
    )
    assert [c[2] for c in copies] == [
        f"Account {member.email} created",
        f"Account {member.email} removed from the organization",
        f"Account {member.email} added to the organization",
    ]
    assert all(c[0] == "platform" and c[1] == super_admin.account_id for c in copies)


async def test_removal_ends_the_sessions_inside_that_organization_only(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin, member, a, b = await member_of_two(browsers, super_admin)
    in_a, member = await ready_member(browsers(), member)
    assert (await choose(in_a, a["id"])).status_code == 200
    in_b = await signed_in(browsers(), member)
    assert (await choose(in_b, b["id"])).status_code == 200
    undecided = await signed_in(browsers(), member)

    removed = await admin.call("DELETE", f"/admin/organizations/{a['id']}/users/{member.user_id}")

    assert removed.status_code == 204, removed.text
    assert (await in_a.call("GET", "/auth/session")).status_code == 401
    assert (await in_b.call("GET", "/scene")).status_code == 200
    session = (await undecided.call("GET", "/auth/session")).json()
    assert [o["id"] for o in session["organizations"]] == [b["id"]]
    assert (await choose(undecided, a["id"])).status_code == 403
    # With one organization left, the next sign-in enters it directly.
    direct = await browsers().sign_in(member.email, member.password)
    assert direct.status_code == 200 and direct.json()["organization"]["id"] == b["id"]
    reasons = await platform_rows(
        "SELECT end_reason::text, tenant_id FROM ontaix.auth_session"
        " WHERE account_id = :a AND end_reason = 'membership_removed'",
        a=member.account_id,
    )
    assert reasons == [("membership_removed", uuid.UUID(a["id"]))]


async def test_disabling_acts_on_the_membership_alone(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin, member, a, b = await member_of_two(browsers, super_admin)
    in_a, member = await ready_member(browsers(), member)
    assert (await choose(in_a, a["id"])).status_code == 200
    in_b = await signed_in(browsers(), member)
    assert (await choose(in_b, b["id"])).status_code == 200
    path = f"/admin/organizations/{a['id']}/users/{member.user_id}"

    disabled = await admin.call("POST", f"{path}/disable")

    assert disabled.status_code == 200 and disabled.json()["status"] == "disabled"
    assert (await in_a.call("GET", "/scene")).status_code == 401
    assert (await in_b.call("GET", "/scene")).status_code == 200
    in_b_users = (await admin.call("GET", f"/admin/organizations/{b['id']}/users")).json()
    assert [u["status"] for u in in_b_users["items"]] == ["active"]
    direct = await browsers().sign_in(member.email, member.password)
    assert direct.status_code == 200 and direct.json()["organization"]["id"] == b["id"]
    assert (await admin.call("POST", f"{path}/disable")).status_code == 200

    enabled = await admin.call("POST", f"{path}/enable")

    assert enabled.status_code == 200 and enabled.json()["status"] == "active"
    both = await browsers().sign_in(member.email, member.password)
    assert both.status_code == 200 and both.json()["organization"] is None
    assert len(both.json()["organizations"]) == 2
    actions = await platform_rows(
        "SELECT action, target_tenant_id FROM ontaix.platform_audit_entry"
        " WHERE target_account_id = :a AND action IN ('account_disabled', 'account_enabled')"
        " ORDER BY id",
        a=member.account_id,
    )
    assert actions == [
        ("account_disabled", uuid.UUID(a["id"])),
        ("account_enabled", uuid.UUID(a["id"])),
    ]
    # Disabled everywhere, the member is refused like a disabled account.
    assert (await admin.call("POST", f"{path}/disable")).status_code == 200
    other = f"/admin/organizations/{b['id']}/users/{b['userId']}"
    assert (await admin.call("POST", f"{other}/disable")).status_code == 200
    everywhere = await browsers().sign_in(member.email, member.password)
    assert everywhere.status_code == 401 and everywhere.json()["code"] == "invalid_credentials"


async def test_a_password_reset_is_for_the_account_in_every_organization(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin, member, a, b = await member_of_two(browsers, super_admin)
    in_a, member = await ready_member(browsers(), member)
    assert (await choose(in_a, a["id"])).status_code == 200
    in_b = await signed_in(browsers(), member)
    assert (await choose(in_b, b["id"])).status_code == 200
    reset_to = generated_password()

    reset = await admin.call(
        "PUT",
        f"/admin/organizations/{a['id']}/users/{member.user_id}/password",
        json={"newPassword": reset_to},
    )

    assert reset.status_code == 204, reset.text
    assert (await in_a.call("GET", "/auth/session")).status_code == 401
    assert (await in_b.call("GET", "/auth/session")).status_code == 401
    assert (await browsers().sign_in(member.email, member.password)).status_code == 401
    after = await browsers().sign_in(member.email, reset_to)
    assert after.status_code == 200 and after.json()["mustChangePassword"] is True
    flags = (await admin.call("GET", f"/admin/organizations/{b['id']}/users")).json()["items"]
    assert [u["mustChangePassword"] for u in flags] == [True]


async def test_adding_an_existing_account_refuses_what_it_must(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    a, b = await create_organization(admin), await create_organization(admin)
    member = await create_member(admin, a["id"])

    unknown = await add_existing(admin, b["id"], f"nobody-{uuid.uuid4().hex[:6]}@org.test")
    assert unknown.status_code == 404 and unknown.json()["code"] == "account_not_found"
    platform = await add_existing(admin, b["id"], super_admin.email)
    assert platform.status_code == 404 and platform.json()["code"] == "account_not_found"
    already = await add_existing(admin, a["id"], member.email)
    assert already.status_code == 409 and already.json()["code"] == "already_member"
    foreign = await add_existing(
        admin, b["id"], member.email, await group_ids(admin, a["id"], "Members")
    )
    assert foreign.status_code == 422 and foreign.json()["errors"][0]["field"] == "groupIds"
    missing = await add_existing(admin, str(uuid.uuid4()), member.email)
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"
    assert (await admin.call("POST", f"/admin/organizations/{b['id']}/disable")).status_code == 200
    off = await add_existing(admin, b["id"], member.email)
    assert off.status_code == 409 and off.json()["code"] == "organization_disabled"
    assert (await admin.call("POST", f"/admin/organizations/{b['id']}/enable")).status_code == 200

    added = await add_existing(admin, b["id"], member.email)

    assert added.status_code == 201, added.text
    assert added.json()["accountId"] == str(member.account_id)
    assert added.json()["id"] != str(member.user_id)
    assert added.json()["email"] == member.email and added.json()["groups"] == []
    twice = await add_existing(admin, b["id"], member.email)
    assert twice.status_code == 409 and twice.json()["code"] == "already_member"
    users = await platform_rows(
        "SELECT tenant_id, issuer, subject FROM ontaix.app_user WHERE email = :e"
        " ORDER BY created_at",
        e=member.email,
    )
    assert users == [
        (uuid.UUID(a["id"]), "local", f"{member.account_id}:{a['id']}"),
        (uuid.UUID(b["id"]), "local", f"{member.account_id}:{b['id']}"),
    ]
    forbidden = await (await ready_member(browsers(), member))[0].call(
        "POST",
        f"/admin/organizations/{b['id']}/memberships",
        json={"email": "x@y.test", "groupIds": []},
    )
    assert forbidden.status_code == 403


async def test_the_two_organizations_of_one_person_never_see_each_other(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin, member, a, b = await member_of_two(browsers, super_admin)
    for org, name in ((a, "Alpha Co"), (b, "Beta Co")):
        owner, _ = await ready_member(
            browsers(),
            await create_member(
                admin, org["id"], await group_ids(admin, org["id"], "Administrators")
            ),
        )
        made = await owner.call(
            "POST", "/companies", json={"name": name, "sub": "one line", "start": "one_cell"}
        )
        assert made.status_code == 201, made.text
    browser, _ = await ready_member(browsers(), member)

    for org, seen, hidden in ((a, "Alpha Co", "Beta Co"), (b, "Beta Co", "Alpha Co")):
        assert (await choose(browser, org["id"])).status_code == 200
        for path in ("/scene", "/companies", "/proposals"):
            response = await browser.call("GET", path)
            assert response.status_code == 200, (path, response.text)
            assert hidden not in response.text, path
        assert seen in (await browser.call("GET", "/scene")).text
    names = await platform_rows(
        "SELECT u.name, u.tenant_id FROM ontaix.app_user u JOIN ontaix.account_membership m"
        " ON m.user_id = u.id WHERE m.account_id = :a",
        a=member.account_id,
    )
    assert {n[1] for n in names} == {uuid.UUID(a["id"]), uuid.UUID(b["id"])}


async def test_a_rename_is_per_organization_while_the_email_is_per_account(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin, member, a, b = await member_of_two(browsers, super_admin)

    renamed = await admin.call(
        "PATCH", f"/admin/organizations/{a['id']}/users/{member.user_id}", json={"name": "In A"}
    )

    assert renamed.status_code == 200 and renamed.json()["name"] == "In A"
    in_b = (await admin.call("GET", f"/admin/organizations/{b['id']}/users")).json()["items"]
    assert [(u["name"], u["email"]) for u in in_b] == [("Member Person", member.email)]
