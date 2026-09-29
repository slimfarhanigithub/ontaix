"""Splitting a speech transcript into segments when the model step does not do it."""

from __future__ import annotations

import re

MAX_SEGMENT_CHARS = 400
MAX_SEGMENTS = 40

_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


def split_transcript(text: str) -> list[tuple[int, int]]:
    """Code-point ranges of the transcript's sentences: split on sentence punctuation and
    newlines, surrounding space left out, a segment over 400 characters cut at its last space
    before 400 (or at 400 when it has none)."""
    segments: list[tuple[int, int]] = []
    start = 0
    for m in [*_BOUNDARY.finditer(text), None]:
        end = m.start() if m else len(text)
        segments.extend(_cut(text, start, end))
        if m:
            start = m.end()
    return segments


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
