"""Whether a rejected spoken label and the label a person then taught are one misheard name.

A speech correction becomes an alias only when the two labels are close in spelling (edit
distance at most a third of the longer label, compared without case) or when the taught label
is a proper name the heard label sounds like. The functions are pure.
"""

from __future__ import annotations

from collections.abc import Collection

from app.utilities.learning_structure import fold
from app.utilities.sound_alike import sounds_like_name

MAX_ALIAS_CHARS = 120
# Characters an alias never holds: markup, controls and invisible format characters, the set the
# `company_alias_text` CHECK refuses.
_REFUSED = frozenset(
    "<> ­؜᠎﻿"
    + "".join(
        chr(c)
        for first, last in ((0x200B, 0x200F), (0x2028, 0x202E), (0x2060, 0x2064), (0x2066, 0x206F))
        for c in range(first, last + 1)
    )
)


def is_alias(heard: str, meant: str, *, company_names: Collection[str]) -> bool:
    """True when `meant` is what a person meant by the misheard `heard`: two different labels
    close in spelling, or `meant` a proper name `heard` sounds like."""
    a, b = fold(heard), fold(meant)
    if not a or not b or a == b or not storable(heard) or not storable(meant):
        return False
    if edit_distance(a, b) * 3 <= max(len(a), len(b)):
        return True
    return sounds_like_name(heard, meant, company_names=company_names)


def storable(label: str) -> bool:
    """True when the label fits an alias: trimmed, 1 to 120 characters, no refused character."""
    return (
        0 < len(label) <= MAX_ALIAS_CHARS
        and label == label.strip()
        and not any(c in _REFUSED or ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F for c in label)
    )


def edit_distance(a: str, b: str) -> int:
    """The Levenshtein distance between two strings."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]
