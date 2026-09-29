"""When the teach extraction model step runs after the rule-based grammar.

The step runs when at least one trigger holds: the grammar understood nothing, or only part of
the sentence; the sentence holds a back-reference word; it holds a list preamble (a count word
or number, one to three words, then `,` or `:`); or it holds a verb form that is not a variant
of the reference lexicon. The verb word list below exists for that check only; the grammar's
lexicon never changes.
"""

from __future__ import annotations

import re
from enum import StrEnum

from app.utilities.teach_parser import CANON, VERB_RE


class Trigger(StrEnum):
    NOT_UNDERSTOOD = "not_understood"
    PARTLY_UNDERSTOOD = "partly_understood"
    BACK_REFERENCE = "back_reference"
    LIST_PREAMBLE = "list_preamble"
    UNKNOWN_VERB = "unknown_verb"


BACK_REFERENCES = frozenset({"these", "those", "it", "they", "them", "this"})

_LIST_PREAMBLE = re.compile(
    r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)"
    r"(?:\s+[^\s,:;.!?]+){1,3}\s*[,:]",
    re.IGNORECASE,
)

_WORD = re.compile(r"[a-z]+(?:-[a-z]+)*")

# Verb forms outside the reference lexicon that mark a sentence the grammar reads wrongly.
# Words that are just as often nouns (orders, plans, costs, services, ...) are left out.
VERB_WORDS = frozenset(
    (
        "sell sells sold selling offer offers offered offering focus focuses focused focusing "
        "focussed specialise specialises specialised specialize specializes specialized "
        "distribute distributes distributed manufacture manufactures manufactured develop "
        "develops developed hire hires hired recruit recruits recruited oversee oversees "
        "oversaw overseen analyse analyses analysed analyze analyzes analyzed collect collects "
        "collected buy buys bought acquire acquires acquired lend lends lent borrow borrows "
        "borrowed invest invests invested earn earns earned spend spends spent write writes "
        "wrote written publish publishes published procure procures procured negotiate "
        "negotiates negotiated compete competes competed organise organises organised organize "
        "organizes organized coordinate coordinates coordinated prepare prepares prepared "
        "promote promotes promoted advertise advertises advertised recommend recommends "
        "recommended advise advises advised consult consults consulted teach teaches taught "
        "learn learns learned learnt comprise comprises comprised involve involves involved "
        "encompass encompasses encompassed enable enables enabled allow allows allowed helps "
        "helped centred centered divide divides divided categorise categorises categorised "
        "categorize categorizes categorized located based sold owned managed operated produced "
        "delivered supplied provided served shipped stored tracked monitored inspected checked "
        "handled governed built created generated designed engineered maintained repaired "
        "installed assembled packed loaded routed processed transformed moved carried "
        "transported approved signed opened closed employed trained certified scheduled "
        "planned assigned received sent placed bought paid invoiced billed issued defined "
        "specified updated followed preceded supported"
    ).split()
)


def fallback_triggers(text: str, grammar_outcome: str) -> set[Trigger]:
    """Every trigger that holds for `text` (the sentence after its domain prefix)."""
    found: set[Trigger] = set()
    if grammar_outcome == "not_understood":
        found.add(Trigger.NOT_UNDERSTOOD)
    elif grammar_outcome == "partly_understood":
        found.add(Trigger.PARTLY_UNDERSTOOD)
    lower = re.sub(r"\s+", " ", text.lower())
    words = _WORD.findall(lower)
    if BACK_REFERENCES.intersection(words):
        found.add(Trigger.BACK_REFERENCE)
    if _LIST_PREAMBLE.search(lower):
        found.add(Trigger.LIST_PREAMBLE)
    outside_lexicon = _WORD.findall(VERB_RE.sub(" ", lower))
    if any(w in VERB_WORDS and w not in CANON for w in outside_lexicon):
        found.add(Trigger.UNKNOWN_VERB)
    return found


def replaces_grammar(triggers: set[Trigger]) -> bool:
    """A valid model answer replaces the grammar's intents unless `partly_understood` alone
    triggered the step, in which case they are merged."""
    return triggers != {Trigger.PARTLY_UNDERSTOOD}
