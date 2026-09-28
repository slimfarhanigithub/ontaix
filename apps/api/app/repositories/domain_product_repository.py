"""Database access for the `domain_product` table."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.domain_product import DomainProduct


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[DomainProduct]:
    result = await session.scalars(
        select(DomainProduct).where(DomainProduct.tenant_id == tenant_id)
    )
    return list(result)


async def get(
    session: AsyncSession, tenant_id: uuid.UUID, domain_product_id: uuid.UUID
) -> DomainProduct | None:
    return await session.scalar(
        select(DomainProduct).where(
            DomainProduct.tenant_id == tenant_id, DomainProduct.id == domain_product_id
        )
    )


async def create(
    session: AsyncSession, tenant_id: uuid.UUID, company_id: uuid.UUID, template_key: str
) -> DomainProduct:
    product = DomainProduct(tenant_id=tenant_id, company_id=company_id, template_key=template_key)
    session.add(product)
    await session.flush()
    return product


async def bump_revision(session: AsyncSession, product: DomainProduct) -> None:
    product.revision += 1
    await session.flush()


async def set_hidden(session: AsyncSession, product: DomainProduct, hidden: bool) -> None:
    product.hidden = hidden
    await session.flush()
