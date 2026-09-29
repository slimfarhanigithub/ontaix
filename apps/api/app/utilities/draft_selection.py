"""Checks on a selection of stored drafts, submitted by index: in range and closed under
`requires`, so every selected draft's parent and relation ends are selected too."""

from __future__ import annotations

from typing import Any


def selection_problem(indexes: list[int], notes: list[dict[str, Any]]) -> str | None:
    """Why the selection cannot be submitted, or None when it can."""
    chosen = set(indexes)
    for index in indexes:
        if index >= len(notes):
            return f"index {index} is not a draft of this result"
    for index in sorted(chosen):
        missing = [r for r in notes[index].get("requires", []) if r not in chosen]
        if missing:
            return f"draft {index} requires draft {missing[0]}, which is not selected"
    return None
