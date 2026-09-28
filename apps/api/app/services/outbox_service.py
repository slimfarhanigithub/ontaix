"""Writes one outbox row per event inside the caller's transaction."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api.actor import Actor
from app.models.storage.base import ActorKind
from app.models.storage.outbox import Outbox
from app.repositories import outbox_repository
from app.utilities.audience import audience

logger = logging.getLogger(__name__)

SUBJECT_PREFIX = "ontaix"
VISIBILITY_MODEL = "model.read"
VISIBILITY_AUDIT = "audit.read"


async def emit(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: Actor,
    event_type: str,
    payload: BaseModel | dict[str, Any],
    *,
    company_ids: Iterable[uuid.UUID] = (),
    visibility: str = VISIBILITY_MODEL,
    bulk: bool = False,
) -> Outbox:
    """Record an event `<aggregate>.<action>` for the relay; the payload is the full new state.

    `visibility` is the permission a subscriber needs to receive the event. `company_ids` is its
    audience: every company whose labels, names or artefact state the payload carries; empty is
    tenant-wide. A subscriber receives the event only when it holds `visibility` in a scope that
    contains every listed company.
    """
    aggregate, action = event_type.split(".", 1)
    body = (
        payload.model_dump(mode="json", by_alias=True)
        if isinstance(payload, BaseModel)
        else payload
    )
    return await outbox_repository.create(
        session,
        tenant_id=tenant_id,
        aggregate=aggregate,
        action=action,
        subject=f"{SUBJECT_PREFIX}.{tenant_id}.{aggregate}.{action}",
        visibility=visibility,
        company_ids=audience(company_ids),
        actor_kind=ActorKind(actor.kind),
        actor_id=actor.id,
        bulk=bulk,
        payload=body,
    )
