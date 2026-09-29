"""Database access for the `teach_session_turn` table: recent sentences of a teach session."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

KEPT_TURNS = 8

_SESSION_KEY = """
    tenant_id = :tenant_id AND actor_kind = CAST(:actor_kind AS ontaix.actor_kind)
    AND actor_id = :actor_id AND company_id = :company_id AND session_id = :session_id
"""

_LOCK = text(
    """
    SELECT pg_advisory_xact_lock(hashtextextended(
        CAST(:tenant_id AS text) || ':' || CAST(:actor_kind AS text) || ':'
        || CAST(:actor_id AS text) || ':' || CAST(:company_id AS text) || ':'
        || CAST(:session_id AS text), 0))
    """
)

_INSERT = text(
    f"""
    INSERT INTO ontaix.teach_session_turn (
        tenant_id, actor_kind, actor_id, company_id, session_id, turn_index, sentence, extractor,
        concept_ids, new_labels)
    SELECT :tenant_id, CAST(:actor_kind AS ontaix.actor_kind), :actor_id, :company_id,
        :session_id, coalesce(max(turn_index) + 1, 0), :sentence, :extractor,
        CAST(:concept_ids AS uuid[]), CAST(:new_labels AS text[])
    FROM ontaix.teach_session_turn WHERE {_SESSION_KEY}
    RETURNING turn_index
    """
)

_TRIM = text(
    f"DELETE FROM ontaix.teach_session_turn WHERE {_SESSION_KEY} AND turn_index <= :oldest_dropped"
)

_RECENT = text(
    f"""
    SELECT turn_index, sentence, extractor, concept_ids, new_labels
    FROM ontaix.teach_session_turn
    WHERE {_SESSION_KEY} AND expires_at > now()
    ORDER BY turn_index DESC LIMIT {KEPT_TURNS}
    """
)


@dataclass(frozen=True)
class SessionKey:
    tenant_id: uuid.UUID
    actor_kind: str
    actor_id: uuid.UUID
    company_id: uuid.UUID
    session_id: uuid.UUID

    def params(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "actor_kind": self.actor_kind,
            "actor_id": self.actor_id,
            "company_id": self.company_id,
            "session_id": self.session_id,
        }


@dataclass(frozen=True)
class StoredTurn:
    turn_index: int
    sentence: str
    extractor: str
    concept_ids: list[uuid.UUID]
    new_labels: list[str]


async def store(
    session: AsyncSession,
    key: SessionKey,
    *,
    sentence: str,
    extractor: str,
    concept_ids: list[uuid.UUID],
    new_labels: list[str],
) -> int:
    """Append one turn under the session's advisory lock and keep the newest 8; the caller
    commits, which releases the lock. The lock is re-entrant within one transaction, so several
    turns stored in one transaction stay together. Returns the turn's index."""
    params = key.params()
    await session.execute(_LOCK, params)
    inserted = await session.execute(
        _INSERT,
        {
            **params,
            "sentence": sentence,
            "extractor": extractor,
            "concept_ids": concept_ids,
            "new_labels": new_labels,
        },
    )
    turn_index = int(inserted.scalar_one())
    await session.execute(_TRIM, {**params, "oldest_dropped": turn_index - KEPT_TURNS})
    return turn_index


async def recent(session: AsyncSession, key: SessionKey) -> list[StoredTurn]:
    """The session's unexpired turns, oldest first, at most 8."""
    rows = (await session.execute(_RECENT, key.params())).all()
    return [
        StoredTurn(r.turn_index, r.sentence, r.extractor, list(r.concept_ids), list(r.new_labels))
        for r in reversed(rows)
    ]


async def delete_expired(session: AsyncSession) -> int:
    result = await session.execute(
        text("DELETE FROM ontaix.teach_session_turn WHERE expires_at <= now()")
    )
    return result.rowcount or 0
