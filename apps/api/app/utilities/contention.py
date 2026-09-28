"""Recognises database errors caused by contention, which the client retries unchanged."""

from __future__ import annotations

from sqlalchemy.exc import DBAPIError

LOCK_NOT_AVAILABLE = "55P03"
DEADLOCK_DETECTED = "40P01"
SERIALIZATION_FAILURE = "40001"
CONTENTION_SQLSTATES = frozenset({LOCK_NOT_AVAILABLE, DEADLOCK_DETECTED, SERIALIZATION_FAILURE})


def is_contention(exc: BaseException) -> bool:
    """True for a lock timeout, a deadlock or a serialisation failure reported by PostgreSQL."""
    return (
        isinstance(exc, DBAPIError) and getattr(exc.orig, "sqlstate", None) in CONTENTION_SQLSTATES
    )
