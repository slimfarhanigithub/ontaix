"""A seeded user holding one role on one scope, for tests of scope-bound rights."""

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
from tests.conftest import DEV_ISSUER, TenantFixture


async def scoped_user(
    session: AsyncSession,
    tenant: TenantFixture,
    role: RoleName,
    scope_kind: ScopeKind,
    *,
    company_id: uuid.UUID | None = None,
    domain_key: str | None = None,
) -> dict[str, str]:
    """Create the user with the grant, commit, and return its request headers."""
    tag = uuid.uuid4().hex[:6]
    subject = f"{role.value}-{scope_kind.value}-{tag}@{tenant.slug}.test"
    user = await app_user_repository.create(
        session,
        tenant_id=tenant.tenant_id,
        issuer=DEV_ISSUER,
        subject=subject,
        email=subject,
        name=f"{role.value} of {scope_kind.value} {tag}",
        department=None,
        company_id=None,
    )
    group = await user_group_repository.create(session, tenant.tenant_id, f"group {tag}", "")
    await group_member_repository.add(session, tenant.tenant_id, group.id, user.id)
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
    return {"X-Ontaix-User": subject}
