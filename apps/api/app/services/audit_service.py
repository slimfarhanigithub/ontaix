"""Appends audit entries and publishes them; other modules only ever call `record`."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.actor import Actor
from app.models.api.audit import AuditEntry as AuditEntryDto
from app.models.storage.app_user import AppUser
from app.models.storage.audit_entry import AuditEntry
from app.models.storage.base import ActorKind, ProposalOrigin
from app.repositories import audit_repository
from app.services import outbox_service
from app.utilities.audience import audience

logger = logging.getLogger(__name__)


async def record(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: Actor,
    kind: str,
    what: str,
    ok: bool,
    proposal_id: uuid.UUID | None = None,
    *,
    company_ids: Iterable[uuid.UUID],
    domain_key: str | None = None,
    origin: ProposalOrigin | None = None,
) -> AuditEntryDto:
    """Append one entry and emit `audit.appended` in the same transaction.

    `company_ids` lists every company the entry names; empty is tenant-wide. `domain_key` is the
    template key of the domain product of the proposal the entry records, None for any other
    entry. `origin` is the origin of the proposal the entry records, None for any other entry.
    The event carries the same audience and key as the entry.
    """
    entry = await audit_repository.create(
        session,
        tenant_id=tenant_id,
        actor_kind=ActorKind(actor.kind),
        actor_user_id=actor.id if actor.kind == "user" else None,
        kind=kind,
        what=what,
        ok=ok,
        proposal_id=proposal_id,
        origin=origin,
        company_ids=audience(company_ids),
        domain_key=domain_key,
    )
    dto = to_dto(entry, {actor.id: actor.name} if actor.id else {})
    await outbox_service.emit(
        session,
        tenant_id,
        actor,
        "audit.appended",
        dto,
        company_ids=entry.company_ids,
        domain_key=entry.domain_key,
        visibility=outbox_service.VISIBILITY_AUDIT,
    )
    return dto


def to_dto(entry: AuditEntry, names: Mapping[uuid.UUID | None, str | None]) -> AuditEntryDto:
    actor_id = entry.actor_user_id if entry.actor_kind is ActorKind.USER else entry.actor_agent_id
    return AuditEntryDto(
        id=entry.id,
        at=entry.at,
        actor=Actor(kind=entry.actor_kind.value, id=actor_id, name=names.get(actor_id)),
        kind=entry.kind,
        what=entry.what,
        ok=entry.ok,
        proposal_id=entry.proposal_id,
        origin=entry.origin.value if entry.origin else None,
        company_ids=list(entry.company_ids),
        domain_key=entry.domain_key,
    )


def user_names(users: list[AppUser]) -> dict[uuid.UUID | None, str | None]:
    return {u.id: u.name for u in users}
