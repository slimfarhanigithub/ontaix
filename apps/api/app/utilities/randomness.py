"""The single random source of the API.

Every random draw goes through `Randomness`. In normal mode it wraps `secrets.SystemRandom`;
when `ONTAIX_TEST_SEED` is set it is a seeded `random.Random`, so test renders are reproducible.
"""

from __future__ import annotations

import random
import secrets
from functools import lru_cache

from app.config import get_settings


class Randomness:
    def __init__(self, seed: int | None) -> None:
        self._rng: random.Random = (
            random.Random(seed) if seed is not None else secrets.SystemRandom()
        )

    def next(self) -> float:
        """A float in [0, 1)."""
        return self._rng.random()

    def range(self, low: int, high: int) -> int:
        """An integer in [low, high]."""
        return self._rng.randint(low, high)


@lru_cache
def get_randomness() -> Randomness:
    """Process-wide random source, seeded from settings when a test seed is present."""
    return Randomness(get_settings().test_seed)
