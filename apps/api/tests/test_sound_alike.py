"""The sound-alike test that keeps a misheard spoken name from becoming a new concept, and
leaves ordinary vocabulary alone."""

from __future__ import annotations

import pytest

from app.utilities.sound_alike import is_proper_name, sounds_like_name

COMPANIES = ("Amdaris", "Insight")

VOCABULARY = [
    ("Employees", "Employers"),
    ("Scales", "Sales"),
    ("Consumers", "Customers"),
    ("Products", "Projects"),
    ("Suppliers", "Supplies"),
    ("Contracts", "Contacts"),
    ("Partners", "Parents"),
    ("Services", "Surfaces"),
    ("Retail", "Retailer"),
    ("Marketing", "Marking"),
]


@pytest.mark.parametrize(("heard", "known"), [*VOCABULARY, *((b, a) for a, b in VOCABULARY)])
def test_ordinary_words_never_sound_like_each_other(heard: str, known: str) -> None:
    assert not sounds_like_name(heard, known, company_names=COMPANIES)


@pytest.mark.parametrize(
    ("heard", "known", "alike"),
    [
        ("Ahmedabus", "Amdaris", True),
        ("Insite", "Insight", True),
        ("Adnock", "ADNOC", True),
        ("Drilling", "Billing", False),
        ("Managed services", "Financial services", False),
        ("Amdaris", "Amdaris", False),
        ("XRG", "XRF", False),
        ("Advisory", "Amdaris", False),
        ("", "Amdaris", False),
    ],
)
def test_a_name_heard_differently_sounds_like_it(heard: str, known: str, alike: bool) -> None:
    assert sounds_like_name(heard, known, company_names=COMPANIES) is alike


def test_only_companies_and_names_with_inner_capitals_are_proper_names() -> None:
    assert is_proper_name("amdaris", COMPANIES)
    assert is_proper_name("ADNOC", ())
    assert is_proper_name("McKinsey", ())
    assert not is_proper_name("Customers", COMPANIES)
    assert not is_proper_name("Financial Services", ())
