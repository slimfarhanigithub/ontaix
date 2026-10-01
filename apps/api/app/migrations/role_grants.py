"""Grant the schema's NOLOGIN roles to the logins the API connects with.

The migrations create `ontaix_app` and `ontaix_platform` and grant them to no login. Every API
connection runs `SET ROLE` to one of them as it opens, which needs membership with the SET
option. A superuser has it for every role. A login that is not a superuser does not: on
PostgreSQL 16, creating a role gives the creator ADMIN OPTION on it but neither INHERIT nor SET,
so on a managed server, where the schema owner is an ordinary administrator login, `SET ROLE`
fails until the role is granted explicitly.

This step grants each role to exactly the login that switches to it, `WITH INHERIT FALSE, SET
TRUE`: the login may become the role, and holds none of the role's privileges outside
`SET ROLE`. It runs with the schema owner's login, which holds ADMIN OPTION on both roles as
their creator (a superuser may run it too), and it is idempotent: a repeated grant is a notice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import psycopg
from psycopg import sql

from app.clients.db_client import APP_ROLE, PLATFORM_ROLE

logger = logging.getLogger(__name__)

_ROLE_EXISTS = "SELECT 1 FROM pg_roles WHERE rolname = %s"
_CAN_SET_ROLE = "SELECT pg_has_role(%s, %s, 'SET')"


@dataclass(frozen=True)
class RoleGrant:
    """One NOLOGIN role granted to one login."""

    role: str
    login: str


class RoleGrantError(Exception):
    """A grant that cannot be made: an unknown login or role, or a grant that did not take."""


def grant_database_roles(database_url: str, app_login: str, platform_login: str) -> list[RoleGrant]:
    """Grant `ontaix_app` to `app_login` and `ontaix_platform` to `platform_login` (the same
    login may be both), in one transaction, and confirm each login can `SET ROLE` to its role.

    `database_url` is the schema owner's connection, which must hold ADMIN OPTION on both roles.
    Nothing else is granted or revoked; a login already holding its role is left as it is.
    """
    grants = [RoleGrant(APP_ROLE, app_login), RoleGrant(PLATFORM_ROLE, platform_login)]
    with psycopg.connect(database_url) as connection:
        for name in sorted({g.role for g in grants} | {g.login for g in grants}):
            if connection.execute(_ROLE_EXISTS, (name,)).fetchone() is None:
                raise RoleGrantError(f"database role {name!r} does not exist")
        for grant in grants:
            connection.execute(
                sql.SQL("GRANT {role} TO {login} WITH INHERIT FALSE, SET TRUE").format(
                    role=sql.Identifier(grant.role), login=sql.Identifier(grant.login)
                )
            )
        for grant in grants:
            row = connection.execute(_CAN_SET_ROLE, (grant.login, grant.role)).fetchone()
            if row is None or not row[0]:
                raise RoleGrantError(f"{grant.login!r} still cannot SET ROLE to {grant.role!r}")
        connection.commit()
    for grant in grants:
        logger.info("%s granted to %s", grant.role, grant.login)
    return grants
