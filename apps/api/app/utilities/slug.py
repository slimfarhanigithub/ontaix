"""Slug of a company name, as the reference builds the company key."""

from __future__ import annotations

import re

NON_ALNUM = re.compile(r"[^a-z0-9]+")


def company_key(name: str) -> str:
    """Lower-case the name and collapse every run of non-alphanumerics into one dash."""
    return NON_ALNUM.sub("-", name.lower())
