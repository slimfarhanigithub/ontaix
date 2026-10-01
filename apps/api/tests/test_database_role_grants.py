"""`python -m app.admin grant-database-roles`: the NOLOGIN roles reach the API's logins.

A schema owner that is not a superuser (the administrator login of a managed server) runs the
migrations, which create `ontaix_app` and `ontaix_platform`, yet cannot `SET ROLE` to them: on
PostgreSQL 16 creating a role gives ADMIN OPTION without SET. The grant step closes that gap for
exactly the logins named, and a second run changes nothing.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

from app import admin as admin_cli
from app.config import get_settings
from app.migrations.role_grants import RoleGrant, RoleGrantError, grant_database_roles
from app.migrations.runner import upgrade_to_head

ROLES = ("ontaix_app", "ontaix_platform")
_MEMBERSHIPS = """
    SELECT r.rolname, m.inherit_option, m.set_option
      FROM pg_auth_members m
      JOIN pg_roles r ON r.oid = m.roleid
      JOIN pg_roles u ON u.oid = m.member
      JOIN pg_roles g ON g.oid = m.grantor
     WHERE u.rolname = %s AND g.rolname = %s AND r.rolname IN ('ontaix_app', 'ontaix_platform')
     ORDER BY 1"""


@dataclass(frozen=True)
class Logins:
    """A scratch database owned and migrated by a login with CREATEROLE but no superuser, and
    two plain logins for the API's pools."""

    owner: str
    api: str
    platform: str
    owner_url: str
    api_url: str
    platform_url: str


@pytest.fixture(scope="module")
def logins(database_url: str) -> Iterator[Logins]:
    tag = uuid.uuid4().hex[:8]
    names = {kind: f"ontaix_{kind}_{tag}" for kind in ("owner", "api", "platform")}
    passwords = {kind: secrets.token_urlsafe(18) for kind in names}
    database = f"ontaix_grants_{tag}"
    with psycopg.connect(database_url, autocommit=True) as admin:
        for kind, options in (("owner", "CREATEROLE"), ("api", ""), ("platform", "")):
            admin.execute(
                sql.SQL(
                    "CREATE ROLE {name} LOGIN NOSUPERUSER {options} PASSWORD {password}"
                ).format(
                    name=sql.Identifier(names[kind]),
                    options=sql.SQL(options),
                    password=sql.Literal(passwords[kind]),
                )
            )
        admin.execute(f'CREATE DATABASE "{database}" OWNER "{names["owner"]}"')
    urls = {
        kind: _login_url(database_url, names[kind], passwords[kind], database) for kind in names
    }
    try:
        upgrade_to_head(urls["owner"])
        with psycopg.connect(database_url, autocommit=True) as admin:
            # The state PostgreSQL 16 leaves when a login without superuser creates a role: the
            # creator administers it, and can neither inherit it nor SET ROLE to it.
            for role in ROLES:
                admin.execute(
                    f'GRANT {role} TO "{names["owner"]}" WITH ADMIN TRUE, INHERIT FALSE, SET FALSE'
                )
        yield Logins(names["owner"], names["api"], names["platform"], *urls.values())
    finally:
        with psycopg.connect(database_url, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
            members = ", ".join(_quoted(n) for n in names.values())
            for role in ROLES:
                admin.execute(f'REVOKE {role} FROM {members} GRANTED BY "{names["owner"]}"')
                admin.execute(f"REVOKE {role} FROM {members} CASCADE")
            for name in names.values():
                admin.execute(f'DROP ROLE IF EXISTS "{name}"')


def test_the_schema_owner_cannot_switch_role_until_granted(logins: Logins) -> None:
    for role in ROLES:
        assert not _can_set_role(logins.owner_url, role)

    grants = grant_database_roles(logins.owner_url, logins.owner, logins.owner)

    assert grants == [
        RoleGrant("ontaix_app", logins.owner),
        RoleGrant("ontaix_platform", logins.owner),
    ]
    for role in ROLES:
        assert _can_set_role(logins.owner_url, role)
    assert _memberships(logins.owner_url, logins.owner, logins.owner) == [
        ("ontaix_app", False, True),
        ("ontaix_platform", False, True),
    ]


def test_a_second_run_changes_nothing(logins: Logins) -> None:
    before = _memberships(logins.owner_url, logins.owner, logins.owner)
    assert grant_database_roles(logins.owner_url, logins.owner, logins.owner) == [
        RoleGrant("ontaix_app", logins.owner),
        RoleGrant("ontaix_platform", logins.owner),
    ]
    assert _memberships(logins.owner_url, logins.owner, logins.owner) == before


def test_separate_logins_hold_only_their_own_role(logins: Logins) -> None:
    grant_database_roles(logins.owner_url, logins.api, logins.platform)

    assert _can_set_role(logins.api_url, "ontaix_app")
    assert not _can_set_role(logins.api_url, "ontaix_platform")
    assert _can_set_role(logins.platform_url, "ontaix_platform")
    assert not _can_set_role(logins.platform_url, "ontaix_app")
    assert _memberships(logins.owner_url, logins.api, logins.owner) == [("ontaix_app", False, True)]
    assert _memberships(logins.owner_url, logins.platform, logins.owner) == [
        ("ontaix_platform", False, True)
    ]


def test_an_unknown_login_is_refused_before_any_grant(logins: Logins) -> None:
    stranger = f"ontaix_nobody_{uuid.uuid4().hex[:8]}"
    with pytest.raises(RoleGrantError, match=stranger):
        grant_database_roles(logins.owner_url, logins.api, stranger)
    assert _memberships(logins.owner_url, logins.api, logins.owner) == [("ontaix_app", False, True)]


def test_the_cli_grants_the_logins_named_in_the_environment(
    logins: Logins, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ONTAIX_DATABASE_URL", logins.owner_url)
    monkeypatch.setenv("ONTAIX_APP_DATABASE_LOGIN", logins.api)
    monkeypatch.delenv("ONTAIX_PLATFORM_DATABASE_LOGIN", raising=False)
    get_settings.cache_clear()
    try:
        assert admin_cli.main(["grant-database-roles"]) == 0
        out = capsys.readouterr()
        assert out.out.splitlines() == [
            f"ontaix_app granted to {logins.api}.",
            f"ontaix_platform granted to {logins.api}.",
        ]
        assert logins.owner_url not in out.out + out.err
        assert _can_set_role(logins.api_url, "ontaix_platform")

        monkeypatch.delenv("ONTAIX_APP_DATABASE_LOGIN")
        get_settings.cache_clear()
        assert admin_cli.main(["grant-database-roles"]) == 2
        assert "ONTAIX_APP_DATABASE_LOGIN" in capsys.readouterr().err

        # A connection without ADMIN OPTION on the roles is refused by the server.
        monkeypatch.setenv("ONTAIX_DATABASE_URL", logins.platform_url)
        monkeypatch.setenv("ONTAIX_APP_DATABASE_LOGIN", logins.platform)
        get_settings.cache_clear()
        assert admin_cli.main(["grant-database-roles"]) == 1
        err = capsys.readouterr().err
        assert "permission denied" in err and logins.platform_url not in err
    finally:
        get_settings.cache_clear()


def _login_url(url: str, login: str, password: str, database: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or "localhost"
    netloc = f"{login}:{password}@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, f"/{database}", parts.query, ""))


def _quoted(name: str) -> str:
    return f'"{name}"'


def _can_set_role(url: str, role: str) -> bool:
    with psycopg.connect(url) as connection:
        try:
            connection.execute(f"SET ROLE {role}")
        except psycopg.errors.InsufficientPrivilege:
            return False
        return connection.execute("SELECT current_user").fetchone() == (role,)


def _memberships(url: str, login: str, grantor: str) -> list[tuple[str, bool, bool]]:
    with psycopg.connect(url) as connection:
        return connection.execute(_MEMBERSHIPS, (login, grantor)).fetchall()
