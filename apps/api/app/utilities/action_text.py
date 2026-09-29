"""Normalisation of relation actions and the characters refused in model-produced text.

Every path that sets a relation action - new relations, relation edits, concept birth actions,
drafts, the batch and teach extraction - compares and stores the same normal form: NFKC,
whitespace runs collapsed to one space, trimmed, lower-cased. `is a` and `equivalent to` are
recognised only on that form.
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")

# Markup, C0 and C1 controls, DEL, U+00A0, U+2028, U+2029 and every Unicode format character
# (category Cf), in the Basic Multilingual Plane and beyond it.
_REFUSED = re.compile(
    "[<>\u0000-\u001f\u007f-\u009f ­؀-؅؜۝܏࢐࢑"
    "࣢᠎​-‏ -‮⁠-⁤⁦-⁯﻿￹-￻"
    "\U000110bd\U000110cd\U00013430-\U0001343f\U0001bca0-\U0001bca3\U0001d173-\U0001d17a"
    "\U000e0001\U000e0020-\U000e007f]"
)


def normalise_action(action: str) -> str:
    """NFKC, whitespace runs collapsed to one space, trimmed, lower-cased."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", action)).strip().lower()


def has_refused_character(text: str) -> bool:
    """True when `text` holds markup, a control, U+00A0, a line separator or a Cf character."""
    return bool(_REFUSED.search(text)) or any(unicodedata.category(c) == "Cf" for c in text)
