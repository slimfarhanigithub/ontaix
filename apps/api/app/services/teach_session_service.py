"""Teach sessions: the last 8 sentences a caller taught one company, kept for 2 hours.

A turn is stored after the parse result is built, in a short transaction of its own under the
session's advisory lock, so concurrent sentences of one session never collide. Storing a turn
is never an error: a failure is logged and the turn is skipped. Only the caller that created a
session reads it, in its tenant and company; an unknown or expired session is empty.
"""

from __future__ import annotations

import logging
import uuid

from app.auth import Caller
from app.clients.db_client import get_session_factory
from app.repositories import teach_session_turn_repository
from app.repositories.teach_session_turn_repository import SessionKey, StoredTurn

logger = logging.getLogger(__name__)

MAX_SENTENCE_CHARS = 400
MAX_IDS = 50
MAX_LABELS = 50


def session_key(caller: Caller, company_id: uuid.UUID, session_id: uuid.UUID) -> SessionKey:
    return SessionKey(
        tenant_id=caller.tenant_id,
        actor_kind=caller.actor_kind.value,
        actor_id=caller.user_id,
        company_id=company_id,
        session_id=session_id,
    )


async def recent_turns(key: SessionKey | None) -> list[StoredTurn]:
    """The session's unexpired turns, oldest first; empty without a session or on failure."""
    if key is None:
        return []
    try:
        async with get_session_factory()() as session:
            return await teach_session_turn_repository.recent(session, key)
    except Exception:
        logger.warning("reading a teach session failed; parsing without its history")
        return []


async def store_turn(
    key: SessionKey | None,
    sentence: str,
    extractor: str,
    concept_ids: list[uuid.UUID],
    new_labels: list[str],
) -> None:
    """Append one turn; a failure skips the turn and never fails the parse."""
    await store_turns(key, extractor, [(sentence, concept_ids, new_labels)])


async def store_turns(
    key: SessionKey | None,
    extractor: str,
    turns: list[tuple[str, list[uuid.UUID], list[str]]],
) -> None:
    """Append a parse's turns in order, in one transaction under the session's advisory lock,
    so no concurrent parse of the session interleaves with them. A failure skips them all and
    never fails the parse."""
    kept = [(t.strip()[:MAX_SENTENCE_CHARS], ids, labels) for t, ids, labels in turns]
    kept = [turn for turn in kept if turn[0]]
    if key is None or not kept:
        return
    try:
        async with get_session_factory()() as session:
            for text, concept_ids, new_labels in kept:
                await teach_session_turn_repository.store(
                    session,
                    key,
                    sentence=text,
                    extractor=extractor,
                    concept_ids=list(dict.fromkeys(concept_ids))[:MAX_IDS],
                    new_labels=[label[:120] for label in dict.fromkeys(new_labels)][:MAX_LABELS],
                )
            await session.commit()
    except Exception:
        logger.warning("storing teach session turns failed; the turns are skipped")


async def purge_expired() -> int:
    """Delete expired turns across tenants, in its own transaction."""
    async with get_session_factory()() as session:
        deleted = await teach_session_turn_repository.delete_expired(session)
        await session.commit()
    return deleted
