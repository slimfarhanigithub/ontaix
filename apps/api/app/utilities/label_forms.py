"""Singular and plural forms of a label, for telling whether two labels name one concept.

`singular_word` is the grammar's `singular` with the irregular English plurals added
(`children`, `people`, `analyses`, `criteria`) and the words whose final `s` is no plural left
alone (`news`, `series`, `species`, the sciences), so `News` and `New` stay two labels. The
grammar's own rule is untouched. In French the plural endings `-s`, `-x` (`-eaux`, `-aux`,
`-eux`, `-oux`) come off and the words whose final `s`, `x` or `z` is no plural stay (`pays`,
`prix`, `gaz`, `processus`); in German the endings `-innen`, `-en`, `-e`, `-n` and a loanword's
`-s` come off, and the plurals that change their vowel or ending (`Häuser`, `Firmen`, `Daten`)
are listed. `label_key` singularises every word of a label, not only the last, so `features
of interest` and `Feature Of Interest` give one key while the punctuation between words is
kept: `L&S` and `L S` stay apart. A French key drops accents and the elided articles
(`l'accueil` and `accueil` are one key); a German key reads `ä`, `ö`, `ü` and `ß` as `ae`,
`oe`, `ue` and `ss` do, so `Straße` and `Strasse` are one key. English keys are unchanged.
"""

from __future__ import annotations

import re
import unicodedata

from app.utilities.language import Language
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
# French plurals in `-aux` whose singular ends in `-ail`, and the other irregular plurals.
FRENCH_IRREGULAR_PLURALS = {
    "travaux": "travail",
    "vitraux": "vitrail",
    "baux": "bail",
    "émaux": "émail",
    "coraux": "corail",
    "soupiraux": "soupirail",
    "yeux": "œil",
    "aïeux": "aïeul",
    "cieux": "ciel",
}
# French singular words ending in `s`, `x` or `z` are invariant; these end in `s` and would
# otherwise lose it.
FRENCH_INVARIANT_WORDS = frozenset(
    {
        "pays",
        "bras",
        "cas",
        "tas",
        "repas",
        "mois",
        "fois",
        "bois",
        "corps",
        "temps",
        "poids",
        "avis",
        "devis",
        "colis",
        "tapis",
        "permis",
        "puits",
        "frais",
        "fonds",
        "cours",
        "concours",
        "secours",
        "recours",
        "parcours",
        "discours",
        "accès",
        "succès",
        "procès",
        "excès",
        "progrès",
        "palais",
        "relais",
        "marais",
        "rabais",
        "biais",
        "univers",
        "divers",
        "mets",
        "mars",
        "sens",
        "engrais",
        "anglais",
        "français",
        "autobus",
        "processus",
        "virus",
        "bonus",
        "campus",
        "consensus",
        "cursus",
        "focus",
        "abus",
        "refus",
        "jus",
        "bus",
        "plus",
        "dos",
        "dessous",
        "dessus",
        "lilas",
        "dans",
        "sous",
        "vers",
        "alors",
    }
)
# German plurals whose singular changes its vowel or its ending, so no suffix rule finds it.
GERMAN_IRREGULAR_PLURALS = {
    "häuser": "haus",
    "kinder": "kind",
    "bilder": "bild",
    "länder": "land",
    "felder": "feld",
    "gelder": "geld",
    "räder": "rad",
    "bänder": "band",
    "wälder": "wald",
    "fächer": "fach",
    "bücher": "buch",
    "dächer": "dach",
    "gläser": "glas",
    "güter": "gut",
    "lichter": "licht",
    "männer": "mann",
    "ämter": "amt",
    "bäder": "bad",
    "blätter": "blatt",
    "rechte": "recht",
    "firmen": "firma",
    "themen": "thema",
    "konten": "konto",
    "risiken": "risiko",
    "daten": "datum",
    "zentren": "zentrum",
    "museen": "museum",
    "kriterien": "kriterium",
    "materialien": "material",
    "prinzipien": "prinzip",
    "praktika": "praktikum",
    "visa": "visum",
    "mütter": "mutter",
    "väter": "vater",
    "töchter": "tochter",
    "brüder": "bruder",
    "städte": "stadt",
    "hände": "hand",
    "wände": "wand",
    "nächte": "nacht",
    "kräfte": "kraft",
    "züge": "zug",
    "flüsse": "fluss",
    "schlüsse": "schluss",
    "anlässe": "anlass",
    "pässe": "pass",
    "köpfe": "kopf",
    "töpfe": "topf",
    "stühle": "stuhl",
    "böden": "boden",
    "läden": "laden",
    "gärten": "garten",
    "öfen": "ofen",
    "mängel": "mangel",
    "kosten": "kosten",
    "leute": "leute",
}
# German loanword plurals in `-s`; a native word's final `s` is no plural (`Haus`, `Kurs`).
GERMAN_S_PLURALS = frozenset(
    {
        "teams",
        "jobs",
        "apps",
        "laptops",
        "tickets",
        "lkws",
        "pkws",
        "chefs",
        "clubs",
        "shops",
        "tools",
        "deals",
        "meetings",
        "workshops",
        "kits",
        "sets",
        "events",
        "parks",
        "hotels",
        "autos",
        "büros",
        "handys",
        "fotos",
        "videos",
        "konzerns",
        "pcs",
        "cafés",
        "restaurants",
        "labels",
        "accounts",
        "services",
        "clients",
        "partners",
        "manager",
    }
)
# A stem a German suffix rule leaves must have at least this many letters.
_GERMAN_MIN_STEM = 3
_TOKENS = re.compile(r"[^\W_]+|[\W_]+")
_FRENCH_ELISION = re.compile(r"\b(?:l|d|qu|j|m|t|s|n|c|jusqu|lorsqu|puisqu)['’](?=\w)")
_GERMAN_FOLDS = (("ß", "ss"), ("ä", "ae"), ("ö", "oe"), ("ü", "ue"))


def singular_word(word: str, language: Language = "en") -> str:
    """The singular of one word in `language`: an irregular plural's singular, an invariant
    word as it is, else the language's rule (for English, the grammar's)."""
    if language == "fr":
        return _french_singular(word)
    if language == "de":
        return _german_singular(word)
    if word in INVARIANT_WORDS:
        return word
    return IRREGULAR_PLURALS.get(word) or singular(word)


def label_key(label: str, language: Language = "en") -> str:
    """`label` as compared with another: NFKC, case folded, every word singular, whitespace
    runs as one space, other punctuation kept, nothing around. A French key has no accents and
    no elided article; a German key spells umlauts and the sharp s out."""
    folded = unicodedata.normalize("NFKC", label).casefold()
    if language == "fr":
        folded = _FRENCH_ELISION.sub("", folded)
    parts = []
    for token in _TOKENS.findall(folded):
        if token[0].isalnum():
            parts.append(_fold_word(singular_word(token, language), language))
        else:
            parts.append(re.sub(r"\s+", " ", token))
    return "".join(parts).strip()


def same_label(a: str, b: str, language: Language = "en") -> bool:
    """True when `a` and `b` name one concept: equal after `label_key`."""
    return label_key(a, language) == label_key(b, language)


def _fold_word(word: str, language: Language) -> str:
    """A singular word as a French or German key spells it; an English word as it is."""
    if language == "fr":
        return strip_accents(word)
    if language == "de":
        for umlaut, spelled in _GERMAN_FOLDS:
            word = word.replace(umlaut, spelled)
        return word
    return word


def strip_accents(word: str) -> str:
    """`word` without accents and other combining marks, `œ` and `æ` spelled out."""
    decomposed = unicodedata.normalize("NFKD", word.replace("œ", "oe").replace("æ", "ae"))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _french_singular(word: str) -> str:
    if word in FRENCH_INVARIANT_WORDS:
        return word
    found = FRENCH_IRREGULAR_PLURALS.get(word)
    if found is not None:
        return found
    if len(word) > 4 and word.endswith("eaux"):
        return word[:-1]
    if len(word) > 4 and word.endswith("aux"):
        return word[:-3] + "al"
    if len(word) > 3 and word.endswith(("eux", "oux")):
        return word[:-1]
    if word.endswith(("x", "z", "ss", "us")):
        return word
    if len(word) > 2 and word.endswith("s"):
        return word[:-1]
    return word


def _german_singular(word: str) -> str:
    found = GERMAN_IRREGULAR_PLURALS.get(word)
    if found is not None:
        return found
    if word in GERMAN_S_PLURALS:
        return word[:-1]
    if word.endswith("innen") and len(word) - 3 >= _GERMAN_MIN_STEM:
        return word[:-3]
    for suffix in ("en", "e", "n"):
        if word.endswith(suffix) and len(word) - len(suffix) >= _GERMAN_MIN_STEM:
            return word[: -len(suffix)]
    if word.endswith("s") and len(word) > 3 and word[-2] in "aeiouy":
        return word[:-1]
    return word
