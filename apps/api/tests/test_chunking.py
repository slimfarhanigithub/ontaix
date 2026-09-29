"""Chunks of a document for whole-document extraction."""

from __future__ import annotations

from app.utilities.chunking import chunk_bounds


def test_chunks_hold_whole_sentences_and_overlap_by_two() -> None:
    assert chunk_bounds([10, 10, 10, 10, 10], 30) == [(0, 3), (1, 4), (2, 5)]
    assert chunk_bounds([50, 10], 30) == [(0, 1), (1, 2)]
    assert chunk_bounds([], 30) == []
    assert chunk_bounds([10] * 3, 1000) == [(0, 3)]
