"""Database access for the `tenant_domain` and `tenant_domain_revision` tables."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.tenant_domain import TenantDomain
from app.models.storage.tenant_domain_revision import TenantDomainRevision

COPY_TEMPLATES_SQL = text(
    """
    INSERT INTO ontaix.tenant_domain
      (tenant_id, key, name, owner, default_color, template_key, position)
    SELECT :tenant_id, t.key, t.name, t.owner, t.color, t.key, t.position
    FROM ontaix.domain_template t
    ON CONFLICT DO NOTHING
    """
)
COPY_TEMPLATE_REVISIONS_SQL = text(
    """
    INSERT INTO ontaix.tenant_domain_revision (tenant_id, key, revision, name, color, owner)
    SELECT d.tenant_id, d.key, 0, d.name, d.default_color, d.owner
    FROM ontaix.tenant_domain d
    WHERE d.tenant_id = :tenant_id
    ON CONFLICT DO NOTHING
    """
)


async def list_in_ring_order(session: AsyncSession, tenant_id: uuid.UUID) -> list[TenantDomain]:
    result = await session.scalars(
        select(TenantDomain)
        .where(TenantDomain.tenant_id == tenant_id)
        .order_by(TenantDomain.position)
    )
    return list(result)


async def copy_templates(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Give a new tenant the nine template domains, each with its revision 0 row."""
    await session.execute(COPY_TEMPLATES_SQL, {"tenant_id": tenant_id})
    await session.execute(COPY_TEMPLATE_REVISIONS_SQL, {"tenant_id": tenant_id})


async def next_position(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    current = await session.scalar(
        select(func.max(TenantDomain.position)).where(TenantDomain.tenant_id == tenant_id)
    )
    return 0 if current is None else int(current) + 1


async def create(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    key: str,
    name: str,
    owner: str,
    color: str,
    position: int,
    proposal_id: uuid.UUID | None,
) -> TenantDomain:
    """A custom domain at revision 0, with its revision row."""
    domain = TenantDomain(
        tenant_id=tenant_id,
        key=key,
        name=name,
        owner=owner,
        default_color=color,
        template_key=None,
        position=position,
        revision=0,
    )
    session.add(domain)
    await session.flush()
    await add_revision(session, domain, color=color, proposal_id=proposal_id)
    return domain


async def update(
    session: AsyncSession,
    domain: TenantDomain,
    *,
    name: str,
    owner: str,
    color: str,
    proposal_id: uuid.UUID | None,
) -> TenantDomain:
    """Rename or re-own the domain, increment its revision and record the new version."""
    domain.name = name
    domain.owner = owner
    domain.revision += 1
    await session.flush()
    await add_revision(session, domain, color=color, proposal_id=proposal_id)
    return domain


async def add_revision(
    session: AsyncSession, domain: TenantDomain, *, color: str, proposal_id: uuid.UUID | None
) -> None:
    session.add(
        TenantDomainRevision(
            tenant_id=domain.tenant_id,
            key=domain.key,
            revision=domain.revision,
            name=domain.name,
            color=color,
            owner=domain.owner,
            proposal_id=proposal_id,
        )
    )
    await session.flush()


async def list_revisions(
    session: AsyncSession, tenant_id: uuid.UUID, key: str
) -> list[TenantDomainRevision]:
    result = await session.scalars(
        select(TenantDomainRevision)
        .where(TenantDomainRevision.tenant_id == tenant_id, TenantDomainRevision.key == key)
        .order_by(TenantDomainRevision.revision)
    )
    return list(result)
