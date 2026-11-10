"""Database access for the `account` table. Reachable only through the platform role."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.account import Account


async def get(session: AsyncSession, account_id: uuid.UUID) -> Account | None:
    return await session.get(Account, account_id, populate_existing=True)


async def get_by_email(session: AsyncSession, email: str) -> Account | None:
    """The account with this already-normalised email."""
    return await session.scalar(
        select(Account).where(Account.email == email).execution_options(populate_existing=True)
    )


async def list_by_ids(session: AsyncSession, ids: set[uuid.UUID]) -> list[Account]:
    if not ids:
        return []
    return list(
        await session.scalars(
            select(Account).where(Account.id.in_(ids)).execution_options(populate_existing=True)
        )
    )


async def create(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    email: str,
    name: str,
    is_platform: bool,
    created_by: uuid.UUID | None,
) -> Account:
    account = Account(
        id=account_id,
        email=email,
        name=name,
        is_platform=is_platform,
        created_by=created_by,
    )
    session.add(account)
    await session.flush()
    return account


async def rename(session: AsyncSession, account_id: uuid.UUID, name: str) -> None:
    await session.execute(
        update(Account)
        .where(Account.id == account_id)
        .values(name=name)
        .execution_options(synchronize_session=False)
    )


async def set_language(session: AsyncSession, account_id: uuid.UUID, language: str | None) -> None:
    """The account's portal language; None follows the browser."""
    await session.execute(
        update(Account)
        .where(Account.id == account_id)
        .values(language=language)
        .execution_options(synchronize_session=False)
    )


async def touch_sign_in(session: AsyncSession, account_id: uuid.UUID) -> None:
    await session.execute(
        update(Account)
        .where(Account.id == account_id)
        .values(last_sign_in_at=func.now())
        .execution_options(synchronize_session=False)
    )
