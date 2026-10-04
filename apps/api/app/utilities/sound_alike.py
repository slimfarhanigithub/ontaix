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

Speech recognition also turns a term it does not know into other words that sound the same
("crowd architects" for "cloud architects", "a jile delivery" for "agile delivery").
`sounds_like_word` says whether one heard word sounds like the word the speaker meant, and
`sound_like_word_together` whether two heard words run together do, by a spelled-out sound
key: letters that spell one sound are written the same way, doubled letters and a silent
trailing e are dropped, and the keys must share most of their letters in order. Short words
never count: "a" tells nothing about "AI".
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
# A heard word and the word meant sound alike when both have this many letters and their sound
# keys share this share of letters in order (difflib's ratio).
MIN_TERM_LETTERS = 4
MIN_SOUND_RATIO = 0.7
MIN_JOINED_SOUND_RATIO = 0.8
# Two heard words join into one only when the first is an article-like fragment ("a", "an").
MAX_JOINED_LEAD_LETTERS = 2

_LETTERS = re.compile(r"[^\W\d_]+")
_SOUNDS = (("ph", "f"), ("ck", "k"), ("q", "k"), ("c", "k"), ("z", "s"), ("x", "ks"))
_SILENT = frozenset("aeiouyhw")
_SILENT_GH = re.compile(r"(?<=[aeiouy])gh")
# Spellings of one sound, applied in order to a word before its letters are compared.
_SOUND_KEY = (
    ("tion", "shen"),
    ("sion", "shen"),
    ("ph", "f"),
    ("ck", "k"),
    ("qu", "kw"),
    ("wr", "r"),
    ("kn", "n"),
    ("wh", "w"),
    ("x", "ks"),
    ("z", "s"),
    ("oo", "u"),
    ("ee", "i"),
    ("ea", "i"),
    ("ou", "u"),
    ("ow", "u"),
    ("ai", "a"),
    ("ay", "a"),
    ("ei", "i"),
    ("ie", "i"),
    ("y", "i"),
)
_SOFT_C = re.compile(r"c(?=[eiy])")
_SOFT_G = re.compile(r"g(?=[eiy])")
_DOUBLED = re.compile(r"(.)\1+")


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


def sounds_like_word(heard: str, meant: str) -> bool:
    """True when one heard word sounds like `meant` but is not that word: both at least four
    letters, and their sound keys sharing at least seven tenths of their letters in order
    ("crowd" and "cloud"; never "sales" and "services")."""
    a, b = "".join(_word_list(heard)), "".join(_word_list(meant))
    if len(a) < MIN_TERM_LETTERS or len(b) < MIN_TERM_LETTERS or singular(a) == singular(b):
        return False
    # A word that holds the other whole is a longer word, not a word misheard: a part of a
    # word never grounds ("report" and "reporting", a suffix split off by a format character).
    # Two spellings of one sound ("insite", "insight") have equal keys and do sound alike.
    ka, kb = sound_key(a), sound_key(b)
    if ka != kb and _contains(ka, kb):
        return False
    return _sound_ratio(a, b) >= MIN_SOUND_RATIO


def sound_like_word_together(first: str, second: str, meant: str) -> bool:
    """True when two heard words run together sound like the one word `meant`, as when a
    leading unstressed syllable is heard as an article ("a jile" and "agile"): the first word
    has at most two letters, the two together at least four, and their sound keys share at
    least eight tenths of their letters in order, a closer match than one word needs, since
    joining words is the larger liberty. "also crowd" never joins into "cloud"."""
    lead = "".join(_word_list(first))
    a, b = lead + "".join(_word_list(second)), "".join(_word_list(meant))
    if not 0 < len(lead) <= MAX_JOINED_LEAD_LETTERS:
        return False
    if len(a) < MIN_TERM_LETTERS or len(b) < MIN_TERM_LETTERS:
        return False
    # The two words together may be the word itself ("a nalytics"); one holding the other
    # whole is a longer word.
    ka, kb = sound_key(a), sound_key(b)
    if ka != kb and _contains(ka, kb):
        return False
    return _sound_ratio(a, b) >= MIN_JOINED_SOUND_RATIO


def _sound_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, sound_key(a), sound_key(b)).ratio()


def _contains(a: str, b: str) -> bool:
    return a in b or b in a


def sound_key(word: str) -> str:
    """The letters of `word` as they sound: one spelling per sound ("ou" and "ow", "ee" and
    "ea", "ph" and "f"), a soft c as s and a soft g as j, doubled letters once, no silent
    trailing e ("solution" as "solushen", "pharmacists" and "farmacists" both as
    "farmasists")."""
    key = _SILENT_GH.sub("", word.casefold())
    for spelled, sound in _SOUND_KEY:
        key = key.replace(spelled, sound)
    key = _SOFT_G.sub("j", _SOFT_C.sub("s", key)).replace("c", "k")
    key = _DOUBLED.sub(r"\1", key)
    return key[:-1] if len(key) > 2 and key.endswith("e") else key


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
