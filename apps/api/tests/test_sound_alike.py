"""The sound-alike test that keeps a misheard spoken name from becoming a new concept, and
leaves ordinary vocabulary alone."""

from __future__ import annotations

import pytest

from app.utilities.sound_alike import company_possessive_rest, is_proper_name, sounds_like_name

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


@pytest.mark.parametrize(
    ("heard", "rest"),
    [
        ("Inside sales", "sales"),
        ("Inside Sales team", "Sales team"),
        ("Insite services", "services"),
        # The name spelled right is a label of its own (Insight AI), never split.
        ("Insight sales", None),
        ("Insight AI", None),
        ("Insights team", None),
        # The name misheard alone is the whole-label test's case, not this one.
        ("Inside", None),
        ("Insider trading", None),
        ("Employees", None),
        ("Engage Insight AI", None),
        ("", None),
    ],
)
def test_a_label_starting_with_the_company_name_misheard_gives_the_rest(
    heard: str, rest: str | None
) -> None:
    assert company_possessive_rest(heard, "Insight") == rest


def test_a_two_word_company_name_is_matched_word_for_word() -> None:
    assert (
        company_possessive_rest("Northbeem Consulting clients", "Northbeam Consulting") == "clients"
    )
    assert company_possessive_rest("Northbeam Consulting clients", "Northbeam Consulting") is None
    assert company_possessive_rest("Amdaris clients", "Amdaris") is None
    assert company_possessive_rest("Ahmedaris clients", "Amdaris") == "clients"
