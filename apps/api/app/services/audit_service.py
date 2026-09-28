"""Appends audit entries and publishes them; other modules only ever call `record`."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.actor import Actor
from app.models.api.audit import AuditEntry as AuditEntryDto
from app.models.storage.app_user import AppUser
from app.models.storage.audit_entry import AuditEntry
from app.models.storage.base import ActorKind
from app.repositories import audit_repository
from app.services import outbox_service

logger = logging.getLogger(__name__)


async def record(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: Actor,
    kind: str,
    what: str,
    ok: bool,
    proposal_id: uuid.UUID | None = None,
) -> AuditEntryDto:
    """Append one entry and emit `audit.appended` in the same transaction."""
    entry = await audit_repository.create(
        session,
        tenant_id=tenant_id,
        actor_kind=ActorKind(actor.kind),
        actor_user_id=actor.id if actor.kind == "user" else None,
        kind=kind,
        what=what,
        ok=ok,
        proposal_id=proposal_id,
    )
    dto = to_dto(entry, {actor.id: actor.name} if actor.id else {})
    await outbox_service.emit(
        session,
        tenant_id,
        actor,
        "audit.appended",
        dto,
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
    )


def user_names(users: list[AppUser]) -> dict[uuid.UUID | None, str | None]:
    return {u.id: u.name for u in users}
