"""Which of a company's lessons a model call receives: BM25 likeness, tier, and a token budget.

Pure functions over the caller's texts, tiers and estimated costs; deterministic, ties going to
the earlier lesson.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.utilities.example_selection import most_similar, within_budget

# The rank of each kind of lesson: a correction first, then an individual approval, then an
# approval made in bulk.
TIER_CORRECT = 0
TIER_APPROVE = 1
TIER_BULK = 2


def select(
    query: str,
    texts: Sequence[str],
    tiers: Sequence[int],
    costs: Sequence[int],
    limit: int,
    budget: int,
) -> list[int]:
    """Indices of the lessons sharing a word with `query`: lower tier first, then higher BM25
    score, at most `limit` whose costs add up to at most `budget`."""
    ranked = most_similar(query, texts)
    position = {i: rank for rank, i in enumerate(ranked)}
    ordered = sorted(ranked, key=lambda i: (tiers[i], position[i]))
    return within_budget(ordered, costs, limit, budget)
