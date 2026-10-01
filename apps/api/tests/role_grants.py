"""Extra personas for tests: a user holding one role on one scope of a test tenant."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import RoleName, ScopeKind
from app.repositories import (
    app_user_repository,
    group_member_repository,
    group_role_repository,
    user_group_repository,
)
from tests.conftest import DEV_ISSUER, Persona, TenantFixture


async def persona_with_role(
    session: AsyncSession,
    tenant: TenantFixture,
    role: RoleName,
    scope_kind: ScopeKind,
    *,
    company_id: uuid.UUID | None = None,
    domain_keys: tuple[str, ...] = (),
) -> Persona:
    """A new user of the tenant holding `role` on the given scope, committed.

    A domain scope is given per key in `domain_keys`: one role assignment per key.
    """
    tag = uuid.uuid4().hex[:6]
    subject = f"{role.value}-{tag}@{tenant.slug}.test"
    user = await app_user_repository.create(
        session,
        tenant_id=tenant.tenant_id,
        issuer=DEV_ISSUER,
        subject=subject,
        email=subject,
        name=f"{role.value} {tag}",
        department=None,
        company_id=None,
    )
    group = await user_group_repository.create(session, tenant.tenant_id, f"{role.value} {tag}", "")
    await group_member_repository.add(session, tenant.tenant_id, group.id, user.id)
    for domain_key in domain_keys or (None,):
        await group_role_repository.create(
            session,
            tenant_id=tenant.tenant_id,
            group_id=group.id,
            role=role,
            scope_kind=scope_kind,
            scope_company_id=company_id,
            scope_domain_key=domain_key,
        )
    await session.commit()
    return Persona(subject=subject, user_id=user.id)
