"""The stage clock: milliseconds per stage, counters, and the recording the harness opens."""

from __future__ import annotations

from app.utilities.stage_clock import StageClock, record_timings


class _Ticks:
    """A clock that advances by the seconds handed to it."""

    def __init__(self) -> None:
        self.now = 10.0

    def __call__(self) -> float:
        return self.now


def test_each_mark_holds_the_time_since_the_previous_one_and_repeats_add_up() -> None:
    ticks = _Ticks()
    clock = StageClock("parse", now=ticks)
    ticks.now += 0.25
    clock.mark("view")
    ticks.now += 1.5
    clock.mark("model")
    ticks.now += 0.1
    clock.mark("view")
    ticks.now += 0.05

    assert clock.total() == 1900
    assert clock.timings.stages == {"view": 350, "model": 1500, "total": 1900}


def test_a_measured_duration_and_counters_travel_with_the_stages() -> None:
    clock = StageClock("extraction", now=_Ticks())
    clock.set("provider_first_token", 420)
    clock.set("ignored", None)
    clock.count("output_tokens", 96)

    assert clock.timings.stages == {"provider_first_token": 420}
    assert clock.timings.counts == {"output_tokens": 96}
    assert str(clock.timings) == "provider_first_token=420ms output_tokens=96"


def test_publishing_lands_in_the_open_recording_only() -> None:
    silent = StageClock("parse", now=_Ticks())
    silent.publish()
    recorded = record_timings()
    clock = StageClock("parse", now=_Ticks())
    clock.mark("view")

    published = clock.publish()

    assert recorded == [published] and published.name == "parse"
