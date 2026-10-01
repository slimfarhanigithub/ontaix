"""`/auth`: sign-in, the lockout, sessions (cookie, expiry, rotation, limit), CSRF, sign-out,
the forced password change and the audit of every attempt."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.auth import SESSION_COOKIE
from app.services import password_hash_service
from tests.auth_helpers import (
    change_password,
    create_member,
    create_organization,
    group_ids,
    platform_execute,
    platform_rows,
    ready_member,
    signed_in,
)
from tests.conftest import TEST_ORIGIN, AccountFixture, Browser, generated_password

INVALID = {"code": "invalid_credentials", "detail": "Email or password is incorrect."}


async def test_sign_in_sets_a_hardened_session_cookie(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    browser = browsers()
    response = await browser.sign_in(super_admin.email.upper(), super_admin.password)

    assert response.status_code == 200, response.text
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    for attribute in ("Path=/", "Secure", "HttpOnly", "SameSite=lax"):
        assert attribute.lower() in cookie.lower()
    assert "max-age" not in cookie.lower() and "domain" not in cookie.lower()
    token = browser.cookie()
    assert token and len(token) == 43
    body = response.json()
    assert token not in response.text
    assert body["kind"] == "platform" and body["platformRoles"] == ["super_admin"]
    assert body["organization"] is None and body["mustChangePassword"] is False
    assert len(body["csrfToken"]) == 43
    stored = await platform_rows(
        "SELECT encode(token_hash, 'hex') FROM ontaix.auth_session WHERE account_id = :a",
        a=super_admin.account_id,
    )
    assert stored and all(token not in row[0] for row in stored)


async def test_every_refusal_answers_the_same_401(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    member = await create_member(admin, org["id"])
    disabled = await create_member(admin, org["id"])
    await admin.call("POST", f"/admin/organizations/{org['id']}/users/{disabled.user_id}/disable")
    other = await create_organization(admin)
    in_disabled_org = await create_member(admin, other["id"])
    await admin.call("POST", f"/admin/organizations/{other['id']}/disable")

    attempts = [
        (member.email, generated_password()),
        ("nobody-" + member.email, generated_password()),
        (disabled.email, disabled.password),
        (in_disabled_org.email, in_disabled_org.password),
    ]
    bodies = []
    for email, password in attempts:
        response = await browsers().sign_in(email, password)
        assert response.status_code == 401, response.text
        bodies.append({k: response.json()[k] for k in ("code", "detail")})
    assert bodies == [INVALID] * 4


async def test_unknown_and_known_emails_cost_one_verification_each(
    browsers: Callable[[], Browser], super_admin: AccountFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    original = password_hash_service._verify
    monkeypatch.setattr(
        password_hash_service, "_verify", lambda h, p: calls.append(h) or original(h, p)
    )

    await browsers().sign_in(super_admin.email, generated_password())
    await browsers().sign_in("nobody-" + super_admin.email, generated_password())

    assert len(calls) == 2


async def test_five_failures_lock_the_email_for_15_minutes(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    member = await create_member(admin, (await create_organization(admin))["id"])
    for _ in range(5):
        response = await browsers().sign_in(member.email, generated_password())
        assert response.status_code == 401

    locked = await browsers().sign_in(member.email, member.password)

    assert locked.status_code == 429, locked.text
    assert locked.json()["code"] == "sign_in_locked"
    assert locked.json()["detail"] == "Too many attempts. Try again in 15 minutes."
    assert 840 < int(locked.headers["Retry-After"]) <= 900

    await platform_execute(
        "UPDATE ontaix.sign_in_throttle SET locked_until = now() - interval '1 second'"
        " WHERE locked_until IS NOT NULL AND key_kind = 'email'"
        " AND key_hash = sha256(convert_to(:e, 'UTF8'))",
        e=member.email,
    )
    assert (await browsers().sign_in(member.email, member.password)).status_code == 200


async def test_five_failures_from_one_address_lock_that_address(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    attacker = browsers()
    for n in range(5):
        response = await attacker.sign_in(f"guess-{n}@nowhere.test", generated_password())
        assert response.status_code == 401

    assert (await attacker.sign_in(super_admin.email, super_admin.password)).status_code == 429
    assert (await browsers().sign_in(super_admin.email, super_admin.password)).status_code == 200


async def test_failures_outside_the_window_start_a_new_count(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    email = f"nobody-{generated_password()[:8].lower()}@nowhere.test"
    for _ in range(4):
        await browsers().sign_in(email, generated_password())
    await platform_execute(
        "UPDATE ontaix.sign_in_throttle SET window_start = now() - interval '16 minutes'"
        " WHERE key_kind = 'email' AND key_hash = sha256(convert_to(:e, 'UTF8'))",
        e=email,
    )

    response = await browsers().sign_in(email, generated_password())

    assert response.status_code == 401, (
        "the fifth failure after the window is the first of a new one"
    )


async def test_a_success_clears_the_email_count(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    for _ in range(4):
        await browsers().sign_in(super_admin.email, generated_password())
    assert (await browsers().sign_in(super_admin.email, super_admin.password)).status_code == 200

    for _ in range(4):
        response = await browsers().sign_in(super_admin.email, generated_password())
        assert response.status_code == 401


async def test_the_lock_names_no_one_and_the_audit_names_no_unknown_email(
    browsers: Callable[[], Browser],
) -> None:
    email = f"ghost-{generated_password()[:8].lower()}@nowhere.test"
    for _ in range(6):
        await browsers().sign_in(email, generated_password())

    rows = await platform_rows(
        "SELECT action, actor_account_id, what FROM ontaix.platform_audit_entry"
        " WHERE what LIKE '%' || :e || '%'",
        e=email,
    )
    assert rows == []


async def test_sign_in_checks_the_origin(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    browser = browsers()
    for headers in ({}, {"Origin": "https://evil.test"}):
        response = await browser.client.post(
            "/auth/sign-in",
            json={"email": super_admin.email, "password": super_admin.password},
            headers=headers,
        )
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "csrf_failed"


async def test_session_read_sign_out_and_a_dead_cookie(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    browser = await signed_in(browsers(), super_admin)
    token = browser.cookie()
    assert (await browser.call("GET", "/auth/session")).status_code == 200

    refused = await browser.client.post("/auth/sign-out", headers={"Origin": TEST_ORIGIN})
    assert refused.status_code == 403 and refused.json()["code"] == "csrf_failed"

    out = await browser.call("POST", "/auth/sign-out")
    assert out.status_code == 204
    assert "max-age=0" in out.headers["set-cookie"].lower()

    replay = await browsers().client.get(
        "/auth/session", headers={"Cookie": f"{SESSION_COOKIE}={token}"}
    )
    assert replay.status_code == 401
    assert (await browsers().call("POST", "/auth/sign-out")).status_code == 204


async def test_sign_in_ends_the_presented_session(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    browser = await signed_in(browsers(), super_admin)
    first = browser.cookie()
    await signed_in(browser, super_admin)

    assert browser.cookie() != first
    rows = await platform_rows(
        "SELECT end_reason FROM ontaix.auth_session"
        " WHERE token_hash = sha256(convert_to(:t, 'UTF8'))",
        t=first,
    )
    assert rows == [("sign_out",)]


TIMEOUTS = {
    "idle": "idle_expires_at = now() - interval '1 second'",
    "absolute": "created_at = now() - interval '13 hours',"
    " absolute_expires_at = now() - interval '1 second',"
    " idle_expires_at = now() - interval '2 seconds'",
}


@pytest.mark.parametrize("timeout", list(TIMEOUTS))
async def test_idle_and_absolute_timeouts_end_the_session(
    browsers: Callable[[], Browser], super_admin: AccountFixture, timeout: str
) -> None:
    browser = await signed_in(browsers(), super_admin)
    await platform_execute(
        f"UPDATE ontaix.auth_session SET {TIMEOUTS[timeout]}"
        " WHERE token_hash = sha256(convert_to(:t, 'UTF8'))",
        t=browser.cookie(),
    )

    response = await browser.call("GET", "/auth/session")

    assert response.status_code == 401
    assert "max-age=0" in response.headers.get("set-cookie", "").lower()
    audited = await platform_rows(
        "SELECT count(*) FROM ontaix.platform_audit_entry"
        " WHERE action = 'session_expired' AND actor_account_id = :a",
        a=super_admin.account_id,
    )
    assert audited[0][0] >= 1


async def test_use_slides_the_idle_timeout_but_never_past_12_hours(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    browser = await signed_in(browsers(), super_admin)
    body = (await browser.call("GET", "/auth/session")).json()
    rows = await platform_rows(
        "SELECT absolute_expires_at - created_at, idle_expires_at - now()"
        " FROM ontaix.auth_session WHERE token_hash = sha256(convert_to(:t, 'UTF8'))",
        t=browser.cookie(),
    )
    absolute, idle = rows[0]
    assert absolute.total_seconds() == 12 * 3600
    assert 29 * 60 < idle.total_seconds() <= 30 * 60
    assert body["idleExpiresAt"] <= body["absoluteExpiresAt"]


async def test_an_account_keeps_at_most_10_live_sessions(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    first = await signed_in(browsers(), super_admin)
    for _ in range(10):
        await signed_in(browsers(), super_admin)

    assert (await first.call("GET", "/auth/session")).status_code == 401
    live = await platform_rows(
        "SELECT count(*) FROM ontaix.auth_session WHERE account_id = :a AND ended_at IS NULL",
        a=super_admin.account_id,
    )
    assert live[0][0] == 10


async def test_a_forced_change_allows_only_the_session_the_change_and_sign_out(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    member = await create_member(admin, org["id"])
    browser = await signed_in(browsers(), member)

    session = (await browser.call("GET", "/auth/session")).json()
    assert session["mustChangePassword"] is True and session["kind"] == "member"
    assert session["organization"]["id"] == org["id"]
    for method, path in (("GET", "/scene"), ("GET", "/companies"), ("POST", "/companies")):
        response = await browser.call(method, path, json={"name": "X"})
        assert response.status_code == 403, (path, response.text)
        assert response.json()["code"] == "password_change_required"


async def test_password_change_rotates_the_token_and_ends_other_sessions(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    member = await create_member(admin, org["id"], await group_ids(admin, org["id"], "Members"))
    other = await signed_in(browsers(), member)
    browser = await signed_in(browsers(), member)
    before = browser.cookie()

    member = await change_password(browser, member)

    assert browser.cookie() != before
    session = (await browser.call("GET", "/auth/session")).json()
    assert session["mustChangePassword"] is False
    assert (await other.call("GET", "/auth/session")).status_code == 401
    assert (await browser.call("GET", "/scene")).status_code == 200
    assert (await browsers().sign_in(member.email, member.password)).status_code == 200
    reasons = await platform_rows(
        "SELECT end_reason FROM ontaix.auth_session WHERE account_id = :a AND ended_at IS NOT NULL",
        a=member.account_id,
    )
    assert {r[0] for r in reasons} == {"password_changed"}


async def test_password_change_refusals(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    member = await create_member(admin, org["id"])
    browser = await signed_in(browsers(), member)

    wrong = await browser.call(
        "PUT",
        "/auth/password",
        json={"currentPassword": generated_password(), "newPassword": generated_password()},
    )
    assert wrong.status_code == 422 and wrong.json()["code"] == "current_password_incorrect"
    for new_password, detail in (
        ("short", "Use at least 12 characters."),
        ("qwerty123456", "This password is too common. Choose another."),
        (member.password, "Choose a password different from the current one."),
        (member.email.split("@")[0] + "-x9", "The password must not contain your email name."),
    ):
        response = await browser.call(
            "PUT",
            "/auth/password",
            json={"currentPassword": member.password, "newPassword": new_password},
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "password_rejected"
        assert response.json()["detail"] == detail

    no_csrf = await browser.client.put(
        "/auth/password",
        json={"currentPassword": member.password, "newPassword": generated_password()},
        headers={"Origin": TEST_ORIGIN},
    )
    assert no_csrf.status_code == 403 and no_csrf.json()["code"] == "csrf_failed"
    failures = await platform_rows(
        "SELECT count(*) FROM ontaix.platform_audit_entry"
        " WHERE action = 'password_change_failed' AND actor_account_id = :a",
        a=member.account_id,
    )
    assert failures[0][0] == 5


async def test_failed_current_password_counts_toward_the_lock(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    member = await create_member(admin, (await create_organization(admin))["id"])
    browser = await signed_in(browsers(), member)
    for _ in range(5):
        await browser.call(
            "PUT",
            "/auth/password",
            json={"currentPassword": generated_password(), "newPassword": generated_password()},
        )

    locked = await browser.call(
        "PUT",
        "/auth/password",
        json={"currentPassword": member.password, "newPassword": generated_password()},
    )

    assert locked.status_code == 429 and locked.json()["code"] == "sign_in_locked"


async def test_cookie_writes_need_the_csrf_token_and_an_allowed_origin(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    member = await create_member(admin, org["id"], await group_ids(admin, org["id"], "Members"))
    browser, _ = await ready_member(browsers(), member)
    body = {"name": "Csrf Co", "sub": "one line", "start": "one_cell"}

    for headers in (
        {"Origin": TEST_ORIGIN},
        {"Origin": TEST_ORIGIN, "X-CSRF-Token": "x" * 43},
        {"Origin": "https://evil.test", "X-CSRF-Token": browser.csrf or ""},
        {"X-CSRF-Token": browser.csrf or ""},
    ):
        response = await browser.client.post("/companies", json=body, headers=headers)
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "csrf_failed"
    assert (await browser.call("GET", "/scene")).status_code == 200


async def test_member_events_are_audited_in_both_logs_without_secrets(
    browsers: Callable[[], Browser], super_admin: AccountFixture
) -> None:
    admin = await signed_in(browsers(), super_admin)
    org = await create_organization(admin)
    member = await create_member(admin, org["id"])
    wrong = generated_password()
    await browsers().sign_in(member.email, wrong)
    browser, member = await ready_member(browsers(), member)
    csrf, cookie = browser.csrf, browser.cookie()
    assert csrf and cookie
    await browser.call("POST", "/auth/sign-out")

    platform = await platform_rows(
        "SELECT action, ok, what FROM ontaix.platform_audit_entry WHERE actor_account_id = :a"
        " ORDER BY id",
        a=member.account_id,
    )
    assert [r[0] for r in platform] == ["sign_in_failed", "sign_in", "password_changed", "sign_out"]
    organization = await platform_rows(
        "SELECT kind, actor_kind::text, what FROM ontaix.audit_entry"
        " WHERE tenant_id = :t AND kind = 'auth' ORDER BY id",
        t=org["id"],
    )
    assert [(r[0], r[1]) for r in organization] == [("auth", "user")] * 4
    everything = " ".join(str(r) for r in [*platform, *organization])
    for secret in (wrong, member.password, csrf, cookie):
        assert secret not in everything
