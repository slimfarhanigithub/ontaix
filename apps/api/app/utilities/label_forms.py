"""Singular and plural forms of a label, for telling whether two labels name one concept.

`singular_word` is the grammar's `singular` with the irregular English plurals added
(`children`, `people`, `analyses`, `criteria`) and the words whose final `s` is no plural left
alone (`news`, `series`, `species`, the sciences), so `News` and `New` stay two labels. The
grammar's own rule is untouched. `label_key` singularises every word of a label, not only the
last, so `features of interest` and `Feature Of Interest` give one key while the punctuation
between words is kept: `L&S` and `L S` stay apart.
"""

from __future__ import annotations

import re
import unicodedata

from app.utilities.teach_parser import singular

IRREGULAR_PLURALS = {
    "children": "child",
    "people": "person",
    "men": "man",
    "women": "woman",
    "chairmen": "chairman",
    "salesmen": "salesman",
    "businessmen": "businessman",
    "feet": "foot",
    "teeth": "tooth",
    "geese": "goose",
    "mice": "mouse",
    "oxen": "ox",
    "criteria": "criterion",
    "phenomena": "phenomenon",
    "analyses": "analysis",
    "crises": "crisis",
    "bases": "basis",
    "theses": "thesis",
    "hypotheses": "hypothesis",
    "diagnoses": "diagnosis",
    "indices": "index",
    "matrices": "matrix",
    "appendices": "appendix",
    "vertices": "vertex",
    "axes": "axis",
}
# Singular words that end in `s`: stripping it would make another word or none.
INVARIANT_WORDS = frozenset(
    {
        "news",
        "series",
        "species",
        "means",
        "status",
        "physics",
        "mathematics",
        "economics",
        "ethics",
        "politics",
        "logistics",
        "analytics",
        "electronics",
        "robotics",
        "genetics",
        "athletics",
        "linguistics",
        "diagnostics",
    }
)
_TOKENS = re.compile(r"[^\W_]+|[\W_]+")


def singular_word(word: str) -> str:
    """The singular of one word: an irregular plural's singular, an invariant word as it is,
    else the grammar's rule."""
    if word in INVARIANT_WORDS:
        return word
    return IRREGULAR_PLURALS.get(word) or singular(word)


def label_key(label: str) -> str:
    """`label` as compared with another: NFKC, case folded, every word singular, whitespace
    runs as one space, other punctuation kept, nothing around."""
    folded = unicodedata.normalize("NFKC", label).casefold()
    parts = []
    for token in _TOKENS.findall(folded):
        if token[0].isalnum():
            parts.append(singular_word(token))
        else:
            parts.append(re.sub(r"\s+", " ", token))
    return "".join(parts).strip()


def same_label(a: str, b: str) -> bool:
    """True when `a` and `b` name one concept: equal after `label_key`."""
    return label_key(a) == label_key(b)
