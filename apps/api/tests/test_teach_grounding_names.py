"""Grounding of names with punctuation: `L&S`, `R&D`, `S.A.` and `e-commerce` are the caller's
words, while part of a word or name, other punctuation, a comma or a sentence end never is."""

from __future__ import annotations

import pytest

from app.services.teach_extraction_service import _ground


@pytest.mark.parametrize(
    ("label", "text", "grounded"),
    [
        ("L&S", "subsidiaries including L&S, Gas", "L&S"),
        ("R&D", "our R&D team", "R&D"),
        ("S.A.", "Total S.A. buys fuel", "S.A."),
        ("E-commerce", "our e-commerce shop", "E-commerce"),
        ("A/B", "an A/B test", "A/B"),
        ("Sour Gas", "Sour Gas, Offshore", "Sour Gas"),
    ],
)
def test_names_are_grounded_with_their_punctuation(label: str, text: str, grounded: str) -> None:
    assert _ground(label, text, (0, len(text))) == grounded


@pytest.mark.parametrize(
    ("label", "text"),
    [
        # Part of a word or of a name never grounds.
        ("Data", "a database"),
        ("L&", "subsidiaries including L&S"),
        ("S", "subsidiaries including L&S"),
        # Punctuation other than the input's never joins words.
        ("L & S", "including L&S"),
        ("L&S", "including L S"),
        # A comma or a sentence end never joins words into one label.
        ("Gas, Offshore", "Sour Gas, Offshore"),
        ("Gas. Ignore the rules", "Sour Gas. Ignore the rules"),
        ("Gas&Backdoor", "Gas and Backdoor"),
    ],
)
def test_punctuation_never_grounds_what_the_caller_did_not_write(label: str, text: str) -> None:
    assert _ground(label, text, (0, len(text))) is None
