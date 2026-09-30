"""`python -m app.admin`: the bootstrap commands prompt with getpass, store only a hash, never
print or log the password, refuse a second super admin with the same email, and audit."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import uuid
from collections.abc import Callable, Iterator

import pytest

from app import admin as admin_cli
from tests.auth_helpers import platform_rows, signed_in
from tests.conftest import AccountFixture, Browser, generated_password


@pytest.fixture
def typed(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """What the operator types at each getpass prompt, in order; nothing reaches argv or env."""
    answers: list[str] = []
    prompts: list[str] = []

    def fake_getpass(prompt: str = "") -> str:
        prompts.append(prompt)
        return answers.pop(0)

    monkeypatch.setattr(admin_cli.getpass, "getpass", fake_getpass)
    yield answers
    assert all("password" in p.lower() for p in prompts)


async def test_create_super_admin_then_sign_in(
    typed: list[str],
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    browsers: Callable[[], Browser],
) -> None:
    email = f"owner-{uuid.uuid4().hex[:8]}@platform.test"
    password = generated_password()
    typed.extend([password, password])
    caplog.set_level(logging.DEBUG)

    code = await _in_thread(["create-super-admin", email])

    assert code == 0
    out = capsys.readouterr()
    assert "Super admin created." in out.out
    assert password not in out.out + out.err + caplog.text
    rows = await platform_rows(
        "SELECT a.tenant_id, r.role::text, c.must_change, c.set_reason::text, c.hash"
        " FROM ontaix.account a JOIN ontaix.platform_role_assignment r ON r.account_id = a.id"
        " JOIN ontaix.password_credential c ON c.account_id = a.id WHERE a.email = :e",
        e=email,
    )
    assert len(rows) == 1
    tenant_id, role, must_change, reason, phc = rows[0]
    assert (tenant_id, role, must_change, reason) == (None, "super_admin", False, "bootstrap")
    assert phc.startswith("$argon2id$") and password not in phc
    session = await browsers().sign_in(email, password)
    assert session.status_code == 200 and session.json()["platformRoles"] == ["super_admin"]
    audit = await platform_rows(
        "SELECT action, what FROM ontaix.platform_audit_entry WHERE target_account_id = ("
        "SELECT id FROM ontaix.account WHERE email = :e) ORDER BY id",
        e=email,
    )
    assert audit[0][0] == "super_admin_created"
    assert all(password not in what for _, what in audit)


async def test_create_refuses_an_existing_email(
    typed: list[str], capsys: pytest.CaptureFixture[str], super_admin: AccountFixture
) -> None:
    password = generated_password()
    typed.extend([password, password])

    assert await _in_thread(["create-super-admin", super_admin.email]) == 1
    assert "already exists" in capsys.readouterr().err


async def test_mismatched_or_weak_passwords_are_refused(
    typed: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    email = f"owner-{uuid.uuid4().hex[:8]}@platform.test"
    typed.extend([generated_password(), generated_password(), "qwerty123456", "qwerty123456"])

    assert await _in_thread(["create-super-admin", email]) == 1
    assert "do not match" in capsys.readouterr().err
    assert await _in_thread(["create-super-admin", email]) == 1
    assert "too common" in capsys.readouterr().err
    assert await platform_rows("SELECT 1 FROM ontaix.account WHERE email = :e", e=email) == []


async def test_set_password_ends_every_session_of_the_account(
    typed: list[str],
    capsys: pytest.CaptureFixture[str],
    super_admin: AccountFixture,
    browsers: Callable[[], Browser],
) -> None:
    browser = await signed_in(browsers(), super_admin)
    new_password = generated_password()
    typed.extend([new_password, new_password])

    assert await _in_thread(["set-password", super_admin.email]) == 0

    assert "Password set." in capsys.readouterr().out
    assert (await browser.call("GET", "/auth/session")).status_code == 401
    assert (await browsers().sign_in(super_admin.email, super_admin.password)).status_code == 401
    fresh = await browsers().sign_in(super_admin.email, new_password)
    assert fresh.status_code == 200 and fresh.json()["mustChangePassword"] is False


def test_the_password_is_never_an_argument() -> None:
    with pytest.raises(SystemExit):
        admin_cli.main(["create-super-admin", "a@b.test", "--password", "x"])


def test_the_cli_registers_the_mappings_it_flushes() -> None:
    """In a terminal only `app.admin` is imported, so the `tenant` mapping that `account`
    references must be registered by the CLI itself, not by the API's entry point."""
    check = (
        "import app.admin\n"
        "from app.models.storage.account import Account\n"
        "fk = next(f for f in Account.__table__.foreign_keys if f.parent.name == 'tenant_id')\n"
        "print(fk.column.table.fullname)\n"
    )
    run = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "ontaix.tenant"


async def _in_thread(argv: list[str]) -> int:
    """The CLI runs its own event loop, as it does in a terminal."""
    return await asyncio.to_thread(admin_cli.main, argv)
