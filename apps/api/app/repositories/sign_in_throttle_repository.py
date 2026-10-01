"""Database access for the `sign_in_throttle` table. Keys are SHA-256 digests, never clear text.

Five failures within 15 minutes lock a key for 15 minutes. Times come from the database clock.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage.base import ThrottleKeyKind
from app.models.storage.sign_in_throttle import SignInThrottle

MAX_FAILURES = 5
WINDOW = "15 minutes"
LOCK = "15 minutes"

_RECORD_FAILURE = text(
    f"""
    INSERT INTO ontaix.sign_in_throttle AS t (key_kind, key_hash, failures, window_start)
    VALUES (CAST(:kind AS ontaix.throttle_key_kind), :key_hash, 1, now())
    ON CONFLICT (key_kind, key_hash) DO UPDATE SET
      failures = CASE WHEN t.window_start <= now() - interval '{WINDOW}' THEN 1
                      ELSE t.failures + 1 END,
      window_start = CASE WHEN t.window_start <= now() - interval '{WINDOW}' THEN now()
                          ELSE t.window_start END
    RETURNING failures
    """
)
_LOCK = text(
    f"""
    UPDATE ontaix.sign_in_throttle
       SET locked_until = now() + interval '{LOCK}', failures = 0, window_start = now()
     WHERE key_kind = CAST(:kind AS ontaix.throttle_key_kind) AND key_hash = :key_hash
    """
)


async def seconds_locked(session: AsyncSession, kind: ThrottleKeyKind, key_hash: bytes) -> int:
    """Whole seconds left on the key's lock, rounded up; 0 when it is not locked."""
    remaining = await session.scalar(
        select(func.extract("epoch", SignInThrottle.locked_until - func.now())).where(
            SignInThrottle.key_kind == kind,
            SignInThrottle.key_hash == key_hash,
            SignInThrottle.locked_until > func.now(),
        )
    )
    if remaining is None:
        return 0
    return max(1, int(-(-float(remaining) // 1)))


async def locked_keys(
    session: AsyncSession, kind: ThrottleKeyKind, key_hashes: set[bytes]
) -> set[bytes]:
    """The keys among `key_hashes` that are locked now."""
    if not key_hashes:
        return set()
    rows = await session.scalars(
        select(SignInThrottle.key_hash).where(
            SignInThrottle.key_kind == kind,
            SignInThrottle.key_hash.in_(key_hashes),
            SignInThrottle.locked_until > func.now(),
        )
    )
    return {bytes(r) for r in rows}


async def record_failure(session: AsyncSession, kind: ThrottleKeyKind, key_hash: bytes) -> bool:
    """Count one failure against the key; True when it reached the limit and is now locked."""
    failures = await session.scalar(_RECORD_FAILURE, {"kind": kind.value, "key_hash": key_hash})
    if failures is not None and failures >= MAX_FAILURES:
        await session.execute(_LOCK, {"kind": kind.value, "key_hash": key_hash})
        return True
    return False


async def clear(session: AsyncSession, kind: ThrottleKeyKind, key_hash: bytes) -> None:
    await session.execute(
        delete(SignInThrottle)
        .where(SignInThrottle.key_kind == kind, SignInThrottle.key_hash == key_hash)
        .execution_options(synchronize_session=False)
    )


async def purge_stale(session: AsyncSession) -> int:
    """Delete keys whose window and lock have both passed."""
    result = await session.execute(
        delete(SignInThrottle)
        .where(
            SignInThrottle.window_start <= func.now() - text(f"interval '{WINDOW}'"),
            (SignInThrottle.locked_until.is_(None)) | (SignInThrottle.locked_until <= func.now()),
        )
        .returning(SignInThrottle.key_hash)
        .execution_options(synchronize_session=False)
    )
    return len(result.all())
