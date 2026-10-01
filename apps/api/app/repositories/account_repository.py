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


async def get_member(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> Account | None:
    """The member account of the organization's directory user."""
    return await session.scalar(
        select(Account)
        .where(Account.tenant_id == tenant_id, Account.user_id == user_id)
        .execution_options(populate_existing=True)
    )


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[Account]:
    return list(
        await session.scalars(
            select(Account)
            .where(Account.tenant_id == tenant_id)
            .execution_options(populate_existing=True)
        )
    )


async def list_by_ids(session: AsyncSession, ids: set[uuid.UUID]) -> list[Account]:
    if not ids:
        return []
    return list(await session.scalars(select(Account).where(Account.id.in_(ids))))


async def count_by_tenant(session: AsyncSession) -> dict[uuid.UUID, int]:
    """Accounts per organization, disabled included."""
    rows = await session.execute(
        select(Account.tenant_id, func.count())
        .where(Account.tenant_id.is_not(None))
        .group_by(Account.tenant_id)
    )
    return {tenant_id: count for tenant_id, count in rows.all()}


async def create(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    email: str,
    name: str,
    tenant_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    created_by: uuid.UUID | None,
) -> Account:
    account = Account(
        id=account_id,
        email=email,
        name=name,
        tenant_id=tenant_id,
        user_id=user_id,
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


async def set_disabled(session: AsyncSession, account_id: uuid.UUID, disabled: bool) -> bool:
    """Disable or enable; False when the account already was in that state."""
    condition = Account.disabled_at.is_(None) if disabled else Account.disabled_at.is_not(None)
    result = await session.execute(
        update(Account)
        .where(Account.id == account_id, condition)
        .values(disabled_at=func.now() if disabled else None)
        .returning(Account.id)
        .execution_options(synchronize_session=False)
    )
    return result.first() is not None


async def touch_sign_in(session: AsyncSession, account_id: uuid.UUID) -> None:
    await session.execute(
        update(Account)
        .where(Account.id == account_id)
        .values(last_sign_in_at=func.now())
        .execution_options(synchronize_session=False)
    )
