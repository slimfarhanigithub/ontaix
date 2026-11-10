"""Database access for the `account_membership` table. Reachable only through the platform role.

A membership is active while it is neither disabled nor removed; whether its organization is
enabled is checked where it matters, through `tenant`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.account_membership import AccountMembership
from app.models.storage.app_user import AppUser
from app.models.storage.tenant import Tenant


async def get(
    session: AsyncSession, account_id: uuid.UUID, tenant_id: uuid.UUID
) -> AccountMembership | None:
    """The account's membership of the organization, removed or not."""
    return await session.scalar(
        select(AccountMembership)
        .where(AccountMembership.account_id == account_id, AccountMembership.tenant_id == tenant_id)
        .execution_options(populate_existing=True)
    )


async def get_by_user(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> AccountMembership | None:
    """The membership behind an organization's directory user, removed or not."""
    return await session.scalar(
        select(AccountMembership)
        .where(AccountMembership.tenant_id == tenant_id, AccountMembership.user_id == user_id)
        .execution_options(populate_existing=True)
    )


async def list_for_account(session: AsyncSession, account_id: uuid.UUID) -> list[AccountMembership]:
    """The account's memberships that are not removed, disabled ones included."""
    return list(
        await session.scalars(
            select(AccountMembership)
            .where(
                AccountMembership.account_id == account_id,
                AccountMembership.removed_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )
    )


async def list_users_for_account(
    session: AsyncSession, account_id: uuid.UUID
) -> list[tuple[AccountMembership, AppUser]]:
    """The account's memberships that are not removed, each with its directory user."""
    rows = await session.execute(
        select(AccountMembership, AppUser)
        .join(
            AppUser,
            (AppUser.tenant_id == AccountMembership.tenant_id)
            & (AppUser.id == AccountMembership.user_id),
        )
        .where(AccountMembership.account_id == account_id, AccountMembership.removed_at.is_(None))
        .execution_options(populate_existing=True)
    )
    return [(membership, user) for membership, user in rows.all()]


async def active_tenants(session: AsyncSession, account_id: uuid.UUID) -> list[Tenant]:
    """The enabled organizations of the account's active memberships, by name."""
    return list(
        await session.scalars(
            select(Tenant)
            .join(AccountMembership, AccountMembership.tenant_id == Tenant.id)
            .where(
                AccountMembership.account_id == account_id,
                AccountMembership.disabled_at.is_(None),
                AccountMembership.removed_at.is_(None),
                Tenant.disabled_at.is_(None),
            )
            .order_by(func.lower(Tenant.name), Tenant.id)
        )
    )


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[AccountMembership]:
    """The organization's memberships that are not removed, disabled ones included."""
    return list(
        await session.scalars(
            select(AccountMembership)
            .where(AccountMembership.tenant_id == tenant_id, AccountMembership.removed_at.is_(None))
            .execution_options(populate_existing=True)
        )
    )


async def count_by_tenant(session: AsyncSession) -> dict[uuid.UUID, int]:
    """Members per organization, disabled included and removed excluded."""
    rows = await session.execute(
        select(AccountMembership.tenant_id, func.count())
        .where(AccountMembership.removed_at.is_(None))
        .group_by(AccountMembership.tenant_id)
    )
    return {tenant_id: count for tenant_id, count in rows.all()}


async def create(
    session: AsyncSession, *, account_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> AccountMembership:
    membership = AccountMembership(account_id=account_id, tenant_id=tenant_id, user_id=user_id)
    session.add(membership)
    await session.flush()
    return membership


async def restore(session: AsyncSession, account_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Bring a removed membership back, enabled, with the same directory user."""
    await session.execute(
        update(AccountMembership)
        .where(AccountMembership.account_id == account_id, AccountMembership.tenant_id == tenant_id)
        .values(removed_at=None, disabled_at=None)
        .execution_options(synchronize_session=False)
    )


async def remove(session: AsyncSession, account_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
    """Record the removal; False when the membership was already removed."""
    result = await session.execute(
        update(AccountMembership)
        .where(
            AccountMembership.account_id == account_id,
            AccountMembership.tenant_id == tenant_id,
            AccountMembership.removed_at.is_(None),
        )
        .values(removed_at=func.now())
        .returning(AccountMembership.user_id)
        .execution_options(synchronize_session=False)
    )
    return result.first() is not None


async def set_disabled(
    session: AsyncSession, account_id: uuid.UUID, tenant_id: uuid.UUID, disabled: bool
) -> bool:
    """Disable or enable the membership; False when it already was in that state."""
    condition = (
        AccountMembership.disabled_at.is_(None)
        if disabled
        else AccountMembership.disabled_at.is_not(None)
    )
    result = await session.execute(
        update(AccountMembership)
        .where(
            AccountMembership.account_id == account_id,
            AccountMembership.tenant_id == tenant_id,
            AccountMembership.removed_at.is_(None),
            condition,
        )
        .values(disabled_at=func.now() if disabled else None)
        .returning(AccountMembership.user_id)
        .execution_options(synchronize_session=False)
    )
    return result.first() is not None
