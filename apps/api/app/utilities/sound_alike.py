"""Whether a spoken label may be a proper name misheard by speech recognition.

Speech recognition turns a spoken name it does not know into other words ("Amdaris" heard as
"ahmedabus"). Ordinary vocabulary is left alone: "Employers" beside "Employees" or "Surfaces"
beside "Services" are different words, and spelling cannot tell them from a misheard name. So
the known label must be a proper name: the name of a company, or a label that carries capitals
inside a word (ADNOC, XRG, McKinsey). Labels are stored with their first letter
capitalised, so a single leading capital says nothing about a name.

A heard label then sounds like the name when both have the same number of words and every word
that differs is a long word whose consonant skeleton and spelling are both close to the name's.
A heard label can also start with the company's name misheard and go on with more words
("Inside sales" for "Insight sales"): the speaker meant the company's own <rest>.
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
_SILENT_GH = re.compile(r"(?<=[aeiouy])gh")


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


def company_possessive_rest(heard: str, company_name: str) -> str | None:
    """The words of `heard` after a leading run that sounds like, but is not spelled as,
    `company_name` ("sales" for "Inside sales" and Insight), keeping their spelling; None when
    `heard` does not start so or has no word after that run."""
    words = heard.split()
    name = _word_list(company_name)
    if not name or len(words) <= len(name):
        return None
    lead = _word_list(" ".join(words[: len(name)]))
    if len(lead) != len(name):
        return None
    differing = [(x, y) for x, y in zip(lead, name, strict=True) if singular(x) != singular(y)]
    if not differing or not all(_close(x, y) for x, y in differing):
        return None
    return " ".join(words[len(name) :])


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
    doubled letters collapsed; a "gh" after a vowel is silent ("insight" as "insit")."""
    word = _SILENT_GH.sub("", word)
    for spelled, sound in _SOUNDS:
        word = word.replace(spelled, sound)
    kept = word[0] + "".join(c for c in word[1:] if c not in _SILENT)
    return re.sub(r"(.)\1+", r"\1", kept)
