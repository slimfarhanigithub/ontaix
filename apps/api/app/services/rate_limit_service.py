"""Per-actor hourly budgets for imports, teach parses and proposal creation.

Each actor of each tenant holds one budget per kind; a budget refills in full at the start of
the next window. A charge takes every unit it asks for or none, and a refused charge answers
`429 rate_limited` with `Retry-After` set to the seconds left in the window. Budgets live in
the process: units spent survive a rolled-back transaction, so a failed call still costs.
"""

from __future__ import annotations

import logging
import math
import threading
import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.utilities.clock import get_clock
from app.utilities.problems import ProblemError

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 3600


class Budget(StrEnum):
    IMPORT = "import"
    PARSE = "parse"
    PROPOSAL = "proposal"


UNITS_PER_WINDOW: dict[Budget, int] = {
    Budget.IMPORT: 60,
    Budget.PARSE: 2000,
    Budget.PROPOSAL: 5000,
}


@dataclass
class _Window:
    started: float
    spent: int


_lock = threading.Lock()
_windows: dict[tuple[Budget, uuid.UUID, str, uuid.UUID], _Window] = {}


def charge(
    budget: Budget, tenant_id: uuid.UUID, actor_kind: str, actor_id: uuid.UUID, units: int = 1
) -> None:
    """Spend `units` of the actor's budget, or refuse the whole call with `429`."""
    if units <= 0:
        return
    now = get_clock().now().timestamp()
    limit = UNITS_PER_WINDOW[budget]
    with _lock:
        key = (budget, tenant_id, actor_kind, actor_id)
        window = _windows.get(key)
        if window is None or now - window.started >= WINDOW_SECONDS:
            window = _Window(started=now, spent=0)
            _windows[key] = window
        if window.spent + units > limit:
            retry_after = max(1, math.ceil(window.started + WINDOW_SECONDS - now))
            raise ProblemError(
                429,
                "rate_limited",
                f"the {budget.value} budget of {limit} units per hour is spent",
                headers={"Retry-After": str(retry_after)},
            )
        window.spent += units


def reset() -> None:
    """Forget every budget; used by tests."""
    with _lock:
        _windows.clear()
