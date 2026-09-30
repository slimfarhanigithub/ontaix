"""A company's habits, derived from what its people approved: the actions they use most and how
they name concepts. Pure functions over the approved actions and labels the caller passes."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from app.utilities.teach_parser import singular

MAX_VERBS = 20
MAX_NAMING = 5
MAX_SUMMARY_CHARS = 300
# A naming pattern is reported when at least this share of the labels it applies to follows it,
# and at least MIN_LABELS labels were approved.
MIN_SHARE = 0.7
MIN_LABELS = 5


def verbs(actions: Iterable[str]) -> list[tuple[str, int]]:
    """The most used actions, most used first, ties in alphabetical order; at most 20."""
    counts = Counter(a.strip().lower() for a in actions if a and a.strip())
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_VERBS]


def naming(labels: Iterable[str]) -> list[str]:
    """Short statements of the naming patterns most labels follow; at most 5."""
    kept = [label.strip() for label in labels if label and label.strip()]
    if len(kept) < MIN_LABELS:
        return []
    out: list[str] = []
    last_words = [label.split()[-1] for label in kept]
    plural = sum(1 for w in last_words if w.isalpha() and singular(w.lower()) != w.lower())
    if plural >= MIN_SHARE * len(kept):
        out.append("labels are plural nouns")
    elif len(kept) - plural >= MIN_SHARE * len(kept):
        out.append("labels are singular nouns")
    multi = [label for label in kept if len(label.split()) > 1]
    if multi:
        title_case = sum(1 for label in multi if all(w[:1].isupper() for w in label.split()))
        sentence_case = sum(1 for label in multi if not any(w[:1].isupper() for w in label.split()[1:]))
        if title_case >= MIN_SHARE * len(multi):
            out.append("every word of a label is capitalised")
        elif sentence_case >= MIN_SHARE * len(multi):
            out.append("only the first word of a label is capitalised")
    acronyms = [w for label in kept for w in label.split() if len(w) >= 2 and w.isalpha() and w.isupper()]
    if acronyms:
        out.append("acronyms kept upper-case")
    short = sum(1 for label in kept if len(label.split()) <= 2)
    if short >= MIN_SHARE * len(kept):
        out.append("labels are one or two words")
    return out[:MAX_NAMING]


def summary(verb_counts: list[tuple[str, int]], patterns: list[str]) -> str:
    """The habits as one line for a model, at most 300 characters; empty when there are none."""
    shown = [v for v, _ in verb_counts]
    while True:
        parts: list[str] = []
        if shown:
            parts.append("Preferred actions: " + ", ".join(shown) + ".")
        if patterns:
            parts.append("Naming: " + "; ".join(patterns) + ".")
        text = " ".join(parts)
        if len(text) <= MAX_SUMMARY_CHARS or not shown:
            return text[:MAX_SUMMARY_CHARS]
        # The least used actions go first until the line fits.
        shown.pop()
