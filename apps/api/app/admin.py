"""`python -m app.admin`: the local bootstrap commands of the platform.

    python -m app.admin create-super-admin <email>
    python -m app.admin set-password <email>

Run by the owner in a terminal attached to the API image (`kubectl exec -it` in the cluster),
with the schema owner's database login in `ONTAIX_DATABASE_URL`: only that login may grant the
platform role. Each command prompts twice for the password with `getpass` (no echo), checks it
against the password policy and stores only its argon2id hash. No command takes the password as
an argument or from an environment variable, prints it, or logs it.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.clients.db_client import async_database_url
from app.config import get_settings

# `account` has a foreign key to `tenant`; its mapping must be registered before the first
# flush, and nothing on this path imports it otherwise.
from app.models.storage import tenant as _tenant_mapping  # noqa: F401
from app.services import super_admin_service
from app.services.super_admin_service import SuperAdminError

logger = logging.getLogger(__name__)

PROMPT = "Password: "
CONFIRM = "Password again: "
Operation = Callable[[AsyncSession, str, str], Awaitable[object]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
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
