"""`python -m app.admin ensure-api-login`: the API's own login holds the two roles and nothing.

The schema owner (a CREATEROLE login that is not a superuser, as the administrator of a managed
server) creates the API's login from the URL the API connects with, grants it `ontaix_app` and
`ontaix_platform` WITH INHERIT FALSE, SET TRUE, and nothing else: the login switches to both
roles, cannot create roles, cannot alter the schema's tables, and holds no right over a table
once it resets its role. A second run changes nothing; a new password in the URL converges.
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
from app.migrations.api_login import ApiLoginError, ensure_api_login, scram_verifier
from app.migrations.role_grants import RoleGrant
from app.migrations.runner import upgrade_to_head

ROLES = ("ontaix_app", "ontaix_platform")
_MEMBERSHIPS = """
    SELECT r.rolname, m.inherit_option, m.set_option
      FROM pg_auth_members m
      JOIN pg_roles r ON r.oid = m.roleid
      JOIN pg_roles u ON u.oid = m.member
     WHERE u.rolname = %s AND r.rolname IN ('ontaix_app', 'ontaix_platform')
     ORDER BY 1"""
_RIGHTS = (
    "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication"
    " FROM pg_roles WHERE rolname = %s"
)
_VERIFIER = "SELECT rolpassword FROM pg_authid WHERE rolname = %s"


@dataclass(frozen=True)
class Server:
    """A scratch database owned and migrated by a CREATEROLE login that is not a superuser, a
    plain login for the refusal cases, and the name and password of the API login to create."""

    superuser_url: str
    owner: str
    owner_url: str
    plain_url: str
    api_login: str
    api_password: str
    api_url: str
    database: str

    def url_for(self, login: str, password: str) -> str:
        return _login_url(self.superuser_url, login, password, self.database)


@pytest.fixture(scope="module")
def server(database_url: str) -> Iterator[Server]:
    tag = uuid.uuid4().hex[:8]
    names = {kind: f"ontaix_{kind}_{tag}" for kind in ("owner", "plain", "apilogin")}
    passwords = {kind: secrets.token_urlsafe(18) for kind in names}
    database = f"ontaix_apilogin_{tag}"
    with psycopg.connect(database_url, autocommit=True) as admin:
        for kind, options in (("owner", "CREATEROLE"), ("plain", "")):
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
    owner_url = _login_url(database_url, names["owner"], passwords["owner"], database)
    plain_url = _login_url(database_url, names["plain"], passwords["plain"], database)
    api_url = _login_url(database_url, names["apilogin"], passwords["apilogin"], database)
    try:
        upgrade_to_head(owner_url)
        with psycopg.connect(database_url, autocommit=True) as admin:
            # What PostgreSQL 16 leaves when a login without superuser creates a role: the
            # creator administers it, and can neither inherit it nor SET ROLE to it.
            for role in ROLES:
                admin.execute(
                    f'GRANT {role} TO "{names["owner"]}" WITH ADMIN TRUE, INHERIT FALSE, SET FALSE'
                )
        yield Server(
            superuser_url=database_url,
            owner=names["owner"],
            owner_url=owner_url,
            plain_url=plain_url,
            api_login=names["apilogin"],
            api_password=passwords["apilogin"],
            api_url=api_url,
            database=database,
        )
    finally:
        with psycopg.connect(database_url, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
            logins = [
                row[0]
                for row in admin.execute(
                    "SELECT rolname FROM pg_roles WHERE rolname LIKE %s", (f"ontaix_%_{tag}%",)
                ).fetchall()
            ]
            members = ", ".join(f'"{name}"' for name in logins)
            for role in ROLES:
                admin.execute(f'REVOKE {role} FROM {members} GRANTED BY "{names["owner"]}"')
                admin.execute(f"REVOKE {role} FROM {members} CASCADE")
            for name in logins:
                if name != names["owner"]:
                    admin.execute(f'REVOKE "{name}" FROM "{names["owner"]}" CASCADE')
            for name in logins:
                admin.execute(f'DROP ROLE IF EXISTS "{name}"')


def test_the_login_is_created_with_both_roles_and_no_server_right(server: Server) -> None:
    result = ensure_api_login(server.owner_url, server.api_url)

    assert result.login == server.api_login and result.created
    assert result.grants == [
        RoleGrant("ontaix_app", server.api_login),
        RoleGrant("ontaix_platform", server.api_login),
    ]
    for role in ROLES:
        assert _can_set_role(server.api_url, role)
    assert _memberships(server.superuser_url, server.api_login) == [
        ("ontaix_app", False, True),
        ("ontaix_platform", False, True),
    ]
    assert _rights(server.superuser_url, server.api_login) == (False, False, False, False, False)
    assert _verifier(server.superuser_url, server.api_login) == scram_verifier(
        server.api_login, server.api_password
    )


def test_the_login_cannot_create_roles_alter_tables_or_reset_into_owner_rights(
    server: Server,
) -> None:
    stranger = f"ontaix_nobody_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(server.api_url, autocommit=True) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(f'CREATE ROLE "{stranger}"')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("ALTER TABLE ontaix.tenant ADD COLUMN probe integer")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("SELECT count(*) FROM ontaix.tenant")

        connection.execute("SET ROLE ontaix_app")
        connection.execute("SELECT count(*) FROM ontaix.tenant")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("ALTER TABLE ontaix.tenant ADD COLUMN probe integer")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("DROP TABLE ontaix.tenant")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(f'CREATE ROLE "{stranger}"')

        connection.execute("RESET ROLE")
        assert connection.execute("SELECT current_user").fetchone() == (server.api_login,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("SELECT count(*) FROM ontaix.tenant")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("ALTER TABLE ontaix.tenant OWNER TO CURRENT_USER")
    with psycopg.connect(server.owner_url) as owner:
        assert owner.execute(
            "SELECT tableowner FROM pg_tables WHERE schemaname = 'ontaix' AND tablename = 'tenant'"
        ).fetchone() == (server.owner,)


def test_a_second_run_changes_nothing(server: Server) -> None:
    before = (
        _memberships(server.superuser_url, server.api_login),
        _verifier(server.superuser_url, server.api_login),
    )

    result = ensure_api_login(server.owner_url, server.api_url)

    assert not result.created
    assert (
        _memberships(server.superuser_url, server.api_login),
        _verifier(server.superuser_url, server.api_login),
    ) == before


def test_a_new_password_in_the_url_converges(server: Server) -> None:
    rotated = secrets.token_urlsafe(18)
    rotated_url = server.url_for(server.api_login, rotated)

    result = ensure_api_login(server.owner_url, rotated_url)

    assert not result.created
    assert _verifier(server.superuser_url, server.api_login) == scram_verifier(
        server.api_login, rotated
    )
    assert _can_set_role(rotated_url, "ontaix_platform")
    ensure_api_login(server.owner_url, server.api_url)
    assert _verifier(server.superuser_url, server.api_login) == scram_verifier(
        server.api_login, server.api_password
    )


def test_the_schema_owner_cannot_be_named_as_the_api_login(server: Server) -> None:
    with pytest.raises(ApiLoginError, match="schema owner"):
        ensure_api_login(server.owner_url, server.owner_url)
    # The owner keeps the memberships of its creation: ADMIN, with neither INHERIT nor SET.
    assert _memberships(server.superuser_url, server.owner) == [
        ("ontaix_app", False, False),
        ("ontaix_platform", False, False),
    ]


def test_a_url_without_credentials_is_refused(server: Server) -> None:
    parts = urlsplit(server.api_url)
    netloc = f"{parts.hostname}:{parts.port}" if parts.port else str(parts.hostname)
    anonymous = urlunsplit((parts.scheme, netloc, parts.path, "", ""))
    with pytest.raises(ApiLoginError, match="ONTAIX_API_DATABASE_URL"):
        ensure_api_login(server.owner_url, anonymous)


def test_a_login_holding_server_rights_is_refused(server: Server) -> None:
    privileged = f"{server.api_login}_cr"
    password = secrets.token_urlsafe(18)
    with psycopg.connect(server.superuser_url, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE ROLE {name} LOGIN CREATEROLE PASSWORD {password}").format(
                name=sql.Identifier(privileged), password=sql.Literal(password)
            )
        )
        admin.execute(f'GRANT "{privileged}" TO "{server.owner}" WITH ADMIN TRUE')

    with pytest.raises(ApiLoginError, match="server-wide rights"):
        ensure_api_login(server.owner_url, server.url_for(privileged, password))

    assert _memberships(server.superuser_url, privileged) == []


def test_the_cli_reads_both_urls_from_the_settings_and_prints_no_url(
    server: Server, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ONTAIX_DATABASE_URL", server.owner_url)
    monkeypatch.setenv("ONTAIX_API_DATABASE_URL", server.api_url)
    get_settings.cache_clear()
    try:
        assert admin_cli.main(["ensure-api-login"]) == 0
        out = capsys.readouterr()
        assert out.out.splitlines() == [
            f"{server.api_login} present, password set.",
            f"ontaix_app granted to {server.api_login}.",
            f"ontaix_platform granted to {server.api_login}.",
        ]
        assert server.api_password not in out.out + out.err

        monkeypatch.delenv("ONTAIX_API_DATABASE_URL")
        get_settings.cache_clear()
        assert admin_cli.main(["ensure-api-login"]) == 2
        assert "ONTAIX_API_DATABASE_URL" in capsys.readouterr().err

        # A connection without CREATEROLE is refused by the server.
        monkeypatch.setenv("ONTAIX_DATABASE_URL", server.plain_url)
        monkeypatch.setenv("ONTAIX_API_DATABASE_URL", server.api_url)
        get_settings.cache_clear()
        assert admin_cli.main(["ensure-api-login"]) == 1
        err = capsys.readouterr().err
        assert "permission denied" in err
        assert server.api_password not in err and server.plain_url not in err
    finally:
        get_settings.cache_clear()


def _login_url(url: str, login: str, password: str, database: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or "localhost"
    netloc = f"{login}:{password}@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, f"/{database}", parts.query, ""))


def _can_set_role(url: str, role: str) -> bool:
    with psycopg.connect(url) as connection:
        try:
            connection.execute(f"SET ROLE {role}")
        except psycopg.errors.InsufficientPrivilege:
            return False
        return connection.execute("SELECT current_user").fetchone() == (role,)


def _memberships(url: str, login: str) -> list[tuple[str, bool, bool]]:
    with psycopg.connect(url) as connection:
        return connection.execute(_MEMBERSHIPS, (login,)).fetchall()


def _rights(url: str, login: str) -> tuple[bool, ...]:
    with psycopg.connect(url) as connection:
        row = connection.execute(_RIGHTS, (login,)).fetchone()
        assert row is not None
        return tuple(row)


def _verifier(url: str, login: str) -> str:
    with psycopg.connect(url) as connection:
        row = connection.execute(_VERIFIER, (login,)).fetchone()
        assert row is not None
        return row[0]
