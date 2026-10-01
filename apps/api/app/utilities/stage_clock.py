"""Wall-clock time per stage of one operation, for the debug log and the evaluation harness.

A `StageClock` marks the end of each named stage; the milliseconds since the previous mark are
added to that stage, so a stage marked twice holds its total. A duration measured elsewhere
(the provider's time to its first token) is set directly, and counters (token counts) travel
with the timings. `record_timings` opens a recording in the current context; every clock
published while it is open lands in that list, so the harness reads the timings of the request
it made without the API returning them.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class StageTimings:
    """Milliseconds per stage of one operation, in the order the stages ended, and counters."""

    name: str
    stages: dict[str, int] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [f"{stage}={ms}ms" for stage, ms in self.stages.items()]
        parts += [f"{key}={value}" for key, value in self.counts.items()]
        return " ".join(parts)


class StageClock:
    def __init__(self, name: str, now: Callable[[], float] = time.perf_counter) -> None:
        self._now = now
        self._started = now()
        self._last = self._started
        self.timings = StageTimings(name)

    def mark(self, stage: str) -> None:
        """Ends `stage` now: the time since the previous mark (or the start) is added to it."""
        now = self._now()
        self.timings.stages[stage] = self.timings.stages.get(stage, 0) + _ms(now - self._last)
        self._last = now

    def set(self, stage: str, ms: int | None) -> None:
        """Records a duration measured elsewhere; None records nothing."""
        if ms is not None:
            self.timings.stages[stage] = ms

    def count(self, key: str, value: int) -> None:
        self.timings.counts[key] = value

    def total(self) -> int:
        """Milliseconds since the clock started, recorded as the stage `total`."""
        total = _ms(self._now() - self._started)
        self.timings.stages["total"] = total
        return total

    def publish(self) -> StageTimings:
        """Hands the timings to the recording open in this context, if any, and returns them."""
        sink = _sink.get()
        if sink is not None:
            sink.append(self.timings)
        return self.timings


_sink: ContextVar[list[StageTimings] | None] = ContextVar("stage_timings", default=None)


def record_timings() -> list[StageTimings]:
    """Starts recording in the current context; returns the list the timings are appended to."""
    timings: list[StageTimings] = []
    _sink.set(timings)
    return timings


def _ms(seconds: float) -> int:
    return max(0, round(seconds * 1000))
