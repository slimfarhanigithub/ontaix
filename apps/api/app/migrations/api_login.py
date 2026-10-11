"""Create the API's own database login and grant it the schema's NOLOGIN roles.

The API connects with a login of its own (`ontaix_api` on Azure) that holds nothing but
membership of `ontaix_app` and `ontaix_platform` WITH INHERIT FALSE, SET TRUE: outside `SET ROLE`
it owns no table and may not alter one, and it can neither create roles nor databases, so a SQL
execution primitive inside the API cannot `RESET ROLE` into the schema owner's rights. The schema
owner's connection (the server administrator, which runs the migrations) creates the login from
the URL the API will connect with, so the password exists in Key Vault and in the server only.

The step is idempotent and converges on every run: a missing login is created, an existing one
is given the password of the URL (Terraform rotates the secret; the pod restarts into the new
value). The password reaches the server as its SCRAM-SHA-256 verifier, never in clear, and the
verifier is deterministic for one login and password, so a repeated run writes the same value.
The grants come from `grant_database_roles`; the step ends by connecting with the API's URL and
switching to both roles.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

import psycopg
from psycopg import sql

from app.clients.db_client import APP_ROLE, PLATFORM_ROLE
from app.migrations.role_grants import RoleGrant, grant_database_roles

logger = logging.getLogger(__name__)

SCRAM_ITERATIONS = 4096
_ROLE_EXISTS = "SELECT 1 FROM pg_roles WHERE rolname = %s"
_ROLE_RIGHTS = (
    "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication"
    " FROM pg_roles WHERE rolname = %s"
)
_ROLE_ATTRIBUTES = sql.SQL(
    "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {password}"
)


@dataclass(frozen=True)
class ApiLogin:
    """The API's login after the step: created on this run or already present, and its grants."""

    login: str
    created: bool
    grants: list[RoleGrant]


class ApiLoginError(Exception):
    """The login cannot be made: a URL without credentials, the schema owner's own login named as
    the API's, or a login that holds server-wide rights. The message never carries a URL."""


def ensure_api_login(admin_url: str, api_url: str) -> ApiLogin:
    """Create the login named in `api_url` with its password (or set that password on it), grant
    it `ontaix_app` and `ontaix_platform`, and confirm the URL connects and switches to both.

    `admin_url` is the schema owner's connection: it creates roles (CREATEROLE) and holds ADMIN
    OPTION on the two NOLOGIN roles as their creator. The login named in `api_url` must differ
    from the owner's, and it never receives SUPERUSER, CREATEROLE, CREATEDB, REPLICATION or
    BYPASSRLS; one found holding any of them is refused.
    """
    login, password = _credentials(api_url, "ONTAIX_API_DATABASE_URL")
    admin_login, _ = _credentials(admin_url, "ONTAIX_DATABASE_URL")
    if login == admin_login:
        raise ApiLoginError(
            f"the API login {login!r} is the schema owner's login; the API connects with its own"
        )
    verifier = sql.Literal(scram_verifier(login, password))
    with psycopg.connect(admin_url) as admin:
        created = admin.execute(_ROLE_EXISTS, (login,)).fetchone() is None
        if created:
            admin.execute(
                sql.SQL("CREATE ROLE {login} ").format(login=sql.Identifier(login))
                + _ROLE_ATTRIBUTES.format(password=verifier)
            )
        else:
            admin.execute(
                sql.SQL("ALTER ROLE {login} WITH LOGIN PASSWORD {password}").format(
                    login=sql.Identifier(login), password=verifier
                )
            )
        rights = admin.execute(_ROLE_RIGHTS, (login,)).fetchone()
        if rights is None or any(rights):
            raise ApiLoginError(
                f"{login!r} holds server-wide rights (superuser, createrole, createdb, bypassrls"
                " or replication); the API login holds none"
            )
        admin.commit()
    grants = grant_database_roles(admin_url, login, login)
    with psycopg.connect(api_url) as connection:
        for role in (APP_ROLE, PLATFORM_ROLE):
            connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            connection.execute("RESET ROLE")
    logger.info("API login %s %s", login, "created" if created else "present, password set")
    return ApiLogin(login, created, grants)


def scram_verifier(login: str, password: str) -> str:
    """The SCRAM-SHA-256 verifier PostgreSQL stores for `password`, as `CREATE ROLE ... PASSWORD`
    accepts it. The salt derives from the login and the password, so the same pair always gives
    the same verifier and a repeated run is a no-op for the server. The password is used as
    given (no SASLprep); the generated passwords are ASCII."""
    salt = hashlib.sha256(f"ontaix-scram:{login}:{password}".encode()).digest()[:16]
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, SCRAM_ITERATIONS)
    client_key = hmac.new(salted, b"Client Key", "sha256").digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", "sha256").digest()
    salt_b64, stored_b64, server_b64 = (
        base64.b64encode(part).decode() for part in (salt, stored_key, server_key)
    )
    return f"SCRAM-SHA-256${SCRAM_ITERATIONS}:{salt_b64}${stored_b64}:{server_b64}"


def _credentials(url: str, setting: str) -> tuple[str, str]:
    """The login and password inside a connection URL; an error naming the setting (never the
    URL) when either is missing."""
    parts = urlsplit(url)
    if not parts.username or parts.password is None:
        raise ApiLoginError(f"{setting} names no login and password")
    return unquote(parts.username), unquote(parts.password)
