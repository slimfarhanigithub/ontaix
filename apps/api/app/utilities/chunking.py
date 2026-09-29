"""A document's sentences cut into chunks for the model: sentence boundaries, bounded size, and
the last sentences of each chunk repeated at the start of the next."""

from __future__ import annotations

OVERLAP_SENTENCES = 2


def chunk_bounds(lengths: list[int], max_chars: int) -> list[tuple[int, int]]:
    """Half-open sentence ranges `[first, end)` of each chunk, in order.

    A chunk holds whole sentences up to `max_chars` code points in all; a sentence longer than
    that is a chunk of its own. Every chunk after the first starts with the last two sentences
    of the one before it, so a structure crossing an edge is read whole, and every chunk adds at
    least one new sentence.
    """
    chunks: list[tuple[int, int]] = []
    start, n = 0, len(lengths)
    while start < n:
        end, size = start, 0
        while end < n and (end == start or size + lengths[end] <= max_chars):
            size += lengths[end]
            end += 1
        chunks.append((start, end))
        if end >= n:
            break
        start = max(end - OVERLAP_SENTENCES, start + 1)
        if start < end and chunks and _only_overlap(lengths, start, end, max_chars):
            start = end
    return chunks


def _only_overlap(lengths: list[int], start: int, end: int, max_chars: int) -> bool:
    """True when the overlap alone leaves no room for the next new sentence."""
    return sum(lengths[start:end]) + lengths[end] > max_chars
