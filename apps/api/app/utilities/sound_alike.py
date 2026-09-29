"""Whether two labels may be the same name misheard by speech recognition.

Speech recognition turns a spoken name it does not know into other words ("Amdaris" heard as
"ahmedabus"). Two labels sound alike when they have the same number of words and every word
that differs is a long word whose consonant skeleton and spelling are both close to the other's.
The test compares spelling only; it never calls anything outside its arguments.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.utilities.teach_parser import singular

# Words shorter than this are never judged misheard: short names (XRG, Gas) differ by design.
MIN_WORD_LETTERS = 5
MIN_SKELETON_RATIO = 0.7
MIN_SPELLING_RATIO = 0.6

_LETTERS = re.compile(r"[^\W\d_]+")
_SOUNDS = (("ph", "f"), ("ck", "k"), ("q", "k"), ("c", "k"), ("z", "s"), ("x", "ks"))
_SILENT = frozenset("aeiouyhw")


def sounds_alike(heard: str, known: str) -> bool:
    """True when `heard` differs from `known` only by words that sound like its words."""
    a, b = _word_list(heard), _word_list(known)
    if not a or len(a) != len(b):
        return False
    differing = [(x, y) for x, y in zip(a, b, strict=True) if singular(x) != singular(y)]
    return bool(differing) and all(_close(x, y) for x, y in differing)


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
