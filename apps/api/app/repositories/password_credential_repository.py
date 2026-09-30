"""Database access for the `password_credential` table. Reachable only through the platform role.

It stores and returns argon2id hashes only; no function here ever takes a password.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import PasswordSetReason
from app.models.storage.password_credential import PasswordCredential

FORCED_CHANGE_REASONS = frozenset({PasswordSetReason.INITIAL, PasswordSetReason.RESET})


async def get(session: AsyncSession, account_id: uuid.UUID) -> PasswordCredential | None:
    return await session.get(PasswordCredential, account_id, populate_existing=True)


async def list_for_accounts(
    session: AsyncSession, account_ids: set[uuid.UUID]
) -> dict[uuid.UUID, PasswordCredential]:
    if not account_ids:
        return {}
    rows = await session.scalars(
        select(PasswordCredential).where(PasswordCredential.account_id.in_(account_ids))
    )
    return {r.account_id: r for r in rows}


async def put(
    session: AsyncSession,
    account_id: uuid.UUID,
    password_hash: str,
    reason: PasswordSetReason,
    set_by: uuid.UUID | None,
) -> None:
    """Store the hash; a password someone else set (initial or reset) must be changed."""
    values = {
        "hash": password_hash,
        "must_change": reason in FORCED_CHANGE_REASONS,
        "set_reason": reason,
        "set_by": set_by,
    }
    statement = insert(PasswordCredential).values(account_id=account_id, **values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[PasswordCredential.account_id],
            set_={**values, "set_at": func.now()},
        )
    )


async def rehash(session: AsyncSession, account_id: uuid.UUID, password_hash: str) -> None:
    """Replace the hash with one of the current parameters, keeping everything else."""
    credential = await get(session, account_id)
    if credential is not None:
        credential.hash = password_hash
        await session.flush()
