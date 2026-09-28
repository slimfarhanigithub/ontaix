"""The single clock of the API; test fixtures freeze it by replacing `now`."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache


class Clock:
    def __init__(self, frozen_at: datetime | None = None) -> None:
        self._frozen_at = frozen_at

    def now(self) -> datetime:
        """The current time, timezone-aware, or the frozen instant in test mode."""
        return self._frozen_at or datetime.now(UTC)

    def freeze(self, at: datetime | None) -> None:
        self._frozen_at = at


@lru_cache
def get_clock() -> Clock:
    return Clock()
