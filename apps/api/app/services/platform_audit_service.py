"""Appends to the platform audit log and, for events of an organization, to its own log.

Every sign-in event and every super admin action goes to `platform_audit_entry`. An event about
a member of an organization, or done inside one, is also written to that organization's
`audit_entry` in the same transaction: kind `auth` for a member's own sign-in, sign-out and
password events, kind `platform` for a super admin's actions (actor kind `platform`).
No entry ever holds a password, a token, a hash, or an email that matches no account.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.actor import Actor
from app.repositories import platform_audit_repository
from app.services import audit_service

logger = logging.getLogger(__name__)

OrganizationAuditKind = Literal["auth", "platform"]


@dataclass(frozen=True)
class OrganizationCopy:
    """The organization's own entry for a platform event."""

    tenant_id: uuid.UUID
    actor: Actor
    kind: OrganizationAuditKind


async def record(
    session: AsyncSession,
    action: str,
    ok: bool,
    what: str,
    *,
    actor_account_id: uuid.UUID | None = None,
    target_tenant_id: uuid.UUID | None = None,
    target_account_id: uuid.UUID | None = None,
    client_ip: str | None = None,
    organization: OrganizationCopy | None = None,
) -> None:
    """Append one platform entry, and the organization's copy when one is given."""
    await platform_audit_repository.create(
        session,
        action=action,
        ok=ok,
        what=what,
        actor_account_id=actor_account_id,
        target_tenant_id=target_tenant_id or (organization.tenant_id if organization else None),
        target_account_id=target_account_id,
        client_ip=client_ip,
    )
    if organization is not None:
        await audit_service.record(
            session,
            organization.tenant_id,
            organization.actor,
            organization.kind,
            what,
            ok,
            company_ids=[],
        )


def platform_actor(account_id: uuid.UUID, name: str) -> Actor:
    """A super admin acting on an organization."""
    return Actor(kind="platform", id=account_id, name=name)


def member_actor(user_id: uuid.UUID, name: str) -> Actor:
    """A member acting on their own account."""
    return Actor(kind="user", id=user_id, name=name)
