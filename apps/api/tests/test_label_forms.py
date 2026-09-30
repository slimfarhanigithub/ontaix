"""Singular and plural forms of a label: which labels name one concept."""

from __future__ import annotations

import pytest

from app.utilities.label_forms import label_key, same_label, singular_word


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("services", "service"),
        ("children", "child"),
        ("people", "person"),
        ("analyses", "analysis"),
        ("criteria", "criterion"),
        ("indices", "index"),
        ("women", "woman"),
        ("news", "news"),
        ("series", "series"),
        ("species", "species"),
        ("logistics", "logistics"),
        ("status", "status"),
        ("bus", "bus"),
        ("class", "class"),
        ("areas", "area"),
        ("new", "new"),
    ],
)
def test_singular_word_knows_irregular_plurals_and_invariant_words(
    word: str, expected: str
) -> None:
    assert singular_word(word) == expected


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("features of interest", "Feature Of Interest"),
        ("Economic events", "economic event"),
        ("Heads of department", "Head of Department"),
        ("Children's services", "Child's service"),
        ("Managed services", "Managed service"),
        ("Points  of sale", "Point of sale"),
        ("Café tables", "Café table"),
    ],
)
def test_labels_that_differ_only_by_the_number_of_any_word_name_one_concept(a: str, b: str) -> None:
    assert same_label(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("News", "New"),
        ("Series", "Sery"),
        ("Sales team", "Sales teams leads"),
        ("L&S", "L S"),
        ("Feature of interest", "Feature of interests today"),
        ("Data", "Date"),
    ],
)
def test_distinct_labels_stay_distinct(a: str, b: str) -> None:
    assert not same_label(a, b)


def test_the_label_key_keeps_punctuation_and_collapses_whitespace() -> None:
    assert label_key("  R&D   Centres ") == "r&d centre"
    assert label_key("O'Neil's") == "o'neil's"
