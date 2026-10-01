"""`python -m app.admin`: the local bootstrap commands of the platform.

    python -m app.admin grant-database-roles
    python -m app.admin create-super-admin <email>
    python -m app.admin set-password <email>

Run by the owner in a terminal attached to the API image (`kubectl exec -it` in the cluster),
with the schema owner's database login in `ONTAIX_DATABASE_URL`: only that login may grant the
platform role. `grant-database-roles` grants `ontaix_app` to the login named by
`ONTAIX_APP_DATABASE_LOGIN` and `ontaix_platform` to the one named by
`ONTAIX_PLATFORM_DATABASE_LOGIN` (default the same login); it takes no password and is safe to
repeat. The password commands prompt twice for the password with `getpass` (no echo), check it
against the password policy and store only its argon2id hash. No command takes the password as
an argument or from an environment variable, prints it, or logs it.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys
from collections.abc import Awaitable, Callable

import psycopg
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.clients.db_client import async_database_url
from app.config import Settings, get_settings
from app.migrations.role_grants import RoleGrantError, grant_database_roles

# `account` has a foreign key to `tenant`; its mapping must be registered before the first
# flush, and nothing on this path imports it otherwise.
from app.models.storage import tenant as _tenant_mapping  # noqa: F401
from app.services import super_admin_service
from app.services.super_admin_service import SuperAdminError

logger = logging.getLogger(__name__)

PROMPT = "Password: "
CONFIRM = "Password again: "
GRANT_COMMAND = "grant-database-roles"
Operation = Callable[[AsyncSession, str, str], Awaitable[object]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        GRANT_COMMAND,
        help="grant ontaix_app and ontaix_platform to the logins named by"
        " ONTAIX_APP_DATABASE_LOGIN and ONTAIX_PLATFORM_DATABASE_LOGIN",
    )
    for name, help_text in (
        ("create-super-admin", "create the platform super admin and set its password"),
        ("set-password", "set the password of any account and end its sessions"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("email")
    args = parser.parse_args(argv)
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    if not settings.database_url:
        print("ONTAIX_DATABASE_URL is not set.", file=sys.stderr)
        return 2
    if args.command == GRANT_COMMAND:
        return _grant_database_roles(settings)
    password = _prompt_password()
    if password is None:
        print("The passwords do not match.", file=sys.stderr)
        return 1
    operation: Operation = (
        super_admin_service.create_super_admin
        if args.command == "create-super-admin"
        else super_admin_service.set_password
    )
    if sys.platform == "win32":
        # psycopg's async driver needs a selector loop; Windows defaults to the proactor loop.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(_run(settings.database_url, operation, args.email, password))
    except SuperAdminError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        password = None
    print("Super admin created." if args.command == "create-super-admin" else "Password set.")
    return 0


def _grant_database_roles(settings: Settings) -> int:
    """Grant each NOLOGIN role to the login named for it; 2 when no login is named, 1 when the
    server refuses (an unknown login, or a connection without ADMIN OPTION on the roles)."""
    app_login = settings.app_database_login
    if not app_login:
        print("ONTAIX_APP_DATABASE_LOGIN is not set.", file=sys.stderr)
        return 2
    platform_login = settings.platform_database_login_or_default()
    assert settings.database_url is not None and platform_login is not None
    try:
        grants = grant_database_roles(settings.database_url, app_login, platform_login)
    except (RoleGrantError, psycopg.Error) as exc:
        print(str(exc).strip(), file=sys.stderr)
        return 1
    for grant in grants:
        print(f"{grant.role} granted to {grant.login}.")
    return 0


def _prompt_password() -> str | None:
    """The password typed twice without echo; None when the two differ."""
    first = getpass.getpass(PROMPT)
    second = getpass.getpass(CONFIRM)
    return first if first == second else None


async def _run(database_url: str, operation: Operation, email: str, password: str) -> None:
    """One transaction on the login's own privileges, committed only when the operation ends
    without a refusal."""
    engine = create_async_engine(async_database_url(database_url), hide_parameters=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await operation(session, email, password)
            await session.commit()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
