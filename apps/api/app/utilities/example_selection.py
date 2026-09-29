"""Lexical selection of worked examples: Okapi BM25 ranking and a token budget.

Pure functions over the caller's strings and numbers; the ranking is deterministic, ties going
to the earlier document.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

# BM25 term-frequency saturation and length normalisation, at their usual values.
K1 = 1.5
B = 0.75

_TOKEN = re.compile(r"\w+")


def tokens(text: str) -> list[str]:
    """The words of `text`, NFKC-normalised and case folded; `_` stays inside a word."""
    return _TOKEN.findall(unicodedata.normalize("NFKC", text).casefold())


def most_similar(query: str, documents: Sequence[str]) -> list[int]:
    """Indices of the documents sharing at least one word with `query`, best BM25 score first;
    equal scores keep document order."""
    docs = [Counter(tokens(d)) for d in documents]
    if not docs:
        return []
    lengths = [sum(d.values()) for d in docs]
    average = sum(lengths) / len(docs) or 1.0
    frequency: Counter[str] = Counter()
    for d in docs:
        frequency.update(d.keys())
    terms = Counter(tokens(query))
    scores: list[tuple[float, int]] = []
    for i, (doc, length) in enumerate(zip(docs, lengths, strict=True)):
        score = 0.0
        for term, count in terms.items():
            tf = doc.get(term, 0)
            if not tf:
                continue
            n = frequency[term]
            idf = math.log(1 + (len(docs) - n + 0.5) / (n + 0.5))
            score += count * idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * length / average))
        if score > 0:
            scores.append((score, i))
    scores.sort(key=lambda s: (-s[0], s[1]))
    return [i for _, i in scores]


def within_budget(
    ranked: Sequence[int], costs: Sequence[int], limit: int, budget: int
) -> list[int]:
    """At most `limit` of `ranked`, in rank order, whose `costs` add up to at most `budget`; an
    entry that would overrun the budget is passed over for the next one."""
    chosen: list[int] = []
    spent = 0
    for i in ranked:
        if len(chosen) >= limit:
            break
        if spent + costs[i] > budget:
            continue
        chosen.append(i)
        spent += costs[i]
    return chosen
