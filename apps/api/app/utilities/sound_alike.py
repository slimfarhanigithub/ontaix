"""Whether a spoken label may be a proper name misheard by speech recognition.

Speech recognition turns a spoken name it does not know into other words ("Amdaris" heard as
"ahmedabus"). Ordinary vocabulary is left alone: "Employers" beside "Employees" or "Surfaces"
beside "Services" are different words, and spelling cannot tell them from a misheard name. So
the known label must be a proper name: the name of a company, or a label that carries capitals
inside a word (ADNOC, XRG, McKinsey). Labels are stored with their first letter
capitalised, so a single leading capital says nothing about a name.

A heard label then sounds like the name when both have the same number of words and every word
that differs is a long word whose consonant skeleton and spelling are both close to the name's.
The test compares spelling only; it never calls anything outside its arguments.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from difflib import SequenceMatcher

from app.utilities.teach_parser import singular

# Words shorter than this are never judged misheard: short names (XRG, Gas) differ by design.
MIN_WORD_LETTERS = 5
MIN_SKELETON_RATIO = 0.75
MIN_SPELLING_RATIO = 0.6

_LETTERS = re.compile(r"[^\W\d_]+")
_SOUNDS = (("ph", "f"), ("ck", "k"), ("q", "k"), ("c", "k"), ("z", "s"), ("x", "ks"))
_SILENT = frozenset("aeiouyhw")


def sounds_like_name(heard: str, known: str, *, company_names: Collection[str]) -> bool:
    """True when `known` is a proper name and `heard` differs from it only by words that sound
    like its words. `company_names` are the names of the tenant's companies."""
    if not is_proper_name(known, company_names):
        return False
    a, b = _word_list(heard), _word_list(known)
    if not a or len(a) != len(b):
        return False
    differing = [(x, y) for x, y in zip(a, b, strict=True) if singular(x) != singular(y)]
    return bool(differing) and all(_close(x, y) for x, y in differing)


def is_proper_name(label: str, company_names: Collection[str]) -> bool:
    """A company's name, or a label with a word that has a capital after its first letter
    (ADNOC, McKinsey); a capital starting a word (Financial Services) is not enough."""
    folded = label.casefold()
    if any(folded == name.casefold() for name in company_names):
        return True
    return any(any(c.isupper() for c in word[1:]) for word in label.split())


def _word_list(label: str) -> list[str]:
    return _LETTERS.findall(label.casefold())


def _close(a: str, b: str) -> bool:
    if len(a) < MIN_WORD_LETTERS or len(b) < MIN_WORD_LETTERS:
        return False
    skeletons = SequenceMatcher(None, _skeleton(a), _skeleton(b)).ratio()
    return (
        skeletons >= MIN_SKELETON_RATIO
        and SequenceMatcher(None, a, b).ratio() >= MIN_SPELLING_RATIO
    )


def _skeleton(word: str) -> str:
    """The word's first letter, then its consonants, with spellings of one sound merged and
    doubled letters collapsed."""
    for spelled, sound in _SOUNDS:
        word = word.replace(spelled, sound)
    kept = word[0] + "".join(c for c in word[1:] if c not in _SILENT)
    return re.sub(r"(.)\1+", r"\1", kept)
