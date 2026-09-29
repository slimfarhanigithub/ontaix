"""The sound-alike test that keeps a misheard spoken name from becoming a new concept."""

from __future__ import annotations

import pytest

from app.utilities.sound_alike import sounds_alike


@pytest.mark.parametrize(
    ("heard", "known", "alike"),
    [
        ("Ahmedabus", "Amdaris", True),
        ("Insite", "Insight", True),
        ("Amdaris Group", "Ahmedabus Group", True),
        ("Drilling", "Billing", False),
        ("Managed services", "Financial services", False),
        ("Customers", "Customer", False),
        ("XRG", "XRF", False),
        ("Soft skills", "Skills", False),
        ("Advisory", "Amdaris", False),
        ("", "Amdaris", False),
    ],
)
def test_sounds_alike(heard: str, known: str, alike: bool) -> None:
    assert sounds_alike(heard, known) is alike
