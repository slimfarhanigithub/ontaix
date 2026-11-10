"""Splitting a speech transcript into segments when the model step does not do it."""

from __future__ import annotations

import re

from app.utilities.language import Language

MAX_SEGMENT_CHARS = 400
MAX_SEGMENTS = 40

_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")
# Abbreviations a French or German recogniser writes with a full stop inside a sentence; a
# boundary right after one is no sentence end. English transcripts are split as before.
_ABBREVIATIONS: dict[Language, frozenset[str]] = {
    "en": frozenset(),
    "fr": frozenset({"m.", "mm.", "mme.", "mlle.", "dr.", "st.", "ste.", "cf.", "p.", "n°."}),
    "de": frozenset(
        {
            "z.",
            "b.",
            "bzw.",
            "nr.",
            "ca.",
            "dr.",
            "str.",
            "usw.",
            "evtl.",
            "ggf.",
            "vgl.",
            "u.",
            "a.",
            "d.",
            "h.",
            "s.",
            "o.",
            "ä.",
            "inkl.",
            "zzgl.",
            "max.",
            "min.",
            "tel.",
            "abs.",
            "art.",
        }
    ),
}


def split_transcript(text: str, language: Language = "en") -> list[tuple[int, int]]:
    """Code-point ranges of the transcript's sentences: split on sentence punctuation and
    newlines, surrounding space left out, a segment over 400 characters cut at its last space
    before 400 (or at 400 when it has none). In French and German a full stop that closes an
    abbreviation (`z. B.`, `M. Dupont`) ends no sentence."""
    abbreviations = _ABBREVIATIONS.get(language, frozenset())
    segments: list[tuple[int, int]] = []
    start = 0
    for m in [*_BOUNDARY.finditer(text), None]:
        if m is not None and _after_abbreviation(text, m.start(), abbreviations):
            continue
        end = m.start() if m else len(text)
        segments.extend(_cut(text, start, end))
        if m:
            start = m.end()
    return segments


def _after_abbreviation(text: str, end: int, abbreviations: frozenset[str]) -> bool:
    """True when the word closing at `end` (its full stop included) is an abbreviation."""
    if not abbreviations or end == 0 or text[end - 1] != ".":
        return False
    at = end - 1
    while at > 0 and not text[at - 1].isspace():
        at -= 1
    return text[at:end].casefold() in abbreviations


def _cut(text: str, start: int, end: int) -> list[tuple[int, int]]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    out: list[tuple[int, int]] = []
    while end - start > MAX_SEGMENT_CHARS:
        space = text.rfind(" ", start + 1, start + MAX_SEGMENT_CHARS)
        stop = space if space > start else start + MAX_SEGMENT_CHARS
        out.append((start, stop))
        start = stop
        while start < end and text[start].isspace():
            start += 1
    if end > start:
        out.append((start, end))
    return out
