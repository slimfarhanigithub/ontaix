"""Scores what the teach pipeline drafted for one case against the tree the case expects.

Pure functions: no I/O. Labels are compared after normalisation (Unicode NFKC, case folding,
punctuation and leading articles removed, last word singular) and through the case's aliases.
Actions are compared after a light verb normalisation and through synonym groups, so "has",
"includes" and "is split into" all count as the same composition action.

Concepts: a drafted concept whose label matches an expected one is a match; its parent, its
action and its path are then checked. The parent is right when it is any of the expected
parents (an ontology class may have several). The path is right when every step from the
concept up to the company root goes through a parent the case accepts for that step, so a
concept placed under an invented or missing intermediate has a wrong path even when its label
and verb are right. The parent is right at the right depth when it is accepted and the concept
sits at its expected level in the drafted tree. A drafted concept that matches nothing expected,
optional or pre-existing is invented; one that repeats a pre-existing concept or an earlier
draft is invented too and listed as a duplicate. A missing branch is a missed concept whose
parent was found (or is the root): the top of a subtree the drafts never reached.

Relations: a drafted relation matches an expected one when it joins the same two concepts, in
either direction; the action is checked against `action` read forward or `inverse` read
backward. An expected relation may also be satisfied by a drafted concept born from one end with
the other as its label, which is how the pipeline records a relation to a concept that did not
exist yet.

Levels: an expected concept's level is its shortest distance from the company root; a drafted
concept's level is its distance in the tree the drafts build on top of the existing concepts.
There is no depth limit. Grounding: an expected concept is groundable when its label or an alias
occurs, whole-word and normalised, in the source text; the share of groundable concepts is the
ceiling any model can reach, and recall is also reported against groundable concepts only.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache

from app.utilities.teach_parser import singular
from evals.teach_case import ExpectedConcept, ExpectedRelation, TeachCase

_LEADING_WORDS = frozenset({"the", "a", "an", "our", "its", "their", "each", "every", "all"})
_NOT_WORD = re.compile(r"[^\w\s]")
_WORD = re.compile(r"\w+")
_UNREACHABLE = 1 << 30

_SYNONYM_GROUPS_RAW: tuple[tuple[str, ...], ...] = (
    (
        "has",
        "includes",
        "contains",
        "comprises",
        "consists of",
        "is made of",
        "is made up of",
        "is composed of",
        "is split into",
        "is divided into",
        "covers",
        "has part",
    ),
    ("sells", "offers", "provides"),
    (
        "focuses on",
        "is focused on",
        "is focused around",
        "focuses around",
        "centres on",
        "centers on",
        "concentrates on",
    ),
    ("is a", "is a kind of", "is a type of", "subclass of"),
)


@dataclass(frozen=True)
class PredictedConcept:
    """A drafted concept (or spec): its label, its parent's label, and its birth action.
    `reverse` means the action reads from the concept to its parent."""

    label: str
    parent: str
    action: str
    reverse: bool = False


@dataclass(frozen=True)
class PredictedRelation:
    source: str
    target: str
    action: str


@dataclass
class LevelScore:
    """One tree level of one case. `correct` counts expected concepts of this level that were
    drafted with a right path; `predicted` counts drafted concepts at this level."""

    expected: int = 0
    groundable: int = 0
    predicted: int = 0
    correct: int = 0
    correct_groundable: int = 0


@dataclass
class CaseScore:
    case_id: str
    kind: str
    concepts_expected: int = 0
    concepts_groundable: int = 0
    concepts_predicted: int = 0
    concepts_matched: int = 0
    matched_groundable: int = 0
    concept_precision: float = 1.0
    concept_recall: float = 1.0
    concept_f1: float = 1.0
    grounding_ceiling: float = 1.0
    concept_recall_groundable: float = 1.0
    concept_f1_groundable: float = 1.0
    parent_correct: int = 0
    # Matched concepts whose parent is accepted and whose drafted level is the expected level.
    parent_at_depth: int = 0
    action_correct: int = 0
    path_correct: int = 0
    invented: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    missing_branches: list[str] = field(default_factory=list)
    optional_drafted: list[str] = field(default_factory=list)
    wrong_parent: list[str] = field(default_factory=list)
    wrong_action: list[str] = field(default_factory=list)
    wrong_path: list[str] = field(default_factory=list)
    wrong_depth: list[str] = field(default_factory=list)
    relations_expected: int = 0
    relations_predicted: int = 0
    relations_matched: int = 0
    relation_precision: float = 1.0
    relation_recall: float = 1.0
    relation_action_correct: int = 0
    invented_relations: list[str] = field(default_factory=list)
    missed_relations: list[str] = field(default_factory=list)
    depth_expected: int = 0
    depth_achieved: int = 0
    levels: dict[int, LevelScore] = field(default_factory=dict)


def normalise_label(label: str) -> str:
    words = _words(label)
    while len(words) > 1 and words[0] in _LEADING_WORDS:
        words = words[1:]
    if words:
        words[-1] = singular(words[-1])
    return " ".join(words)


def normalise_action(action: str) -> str:
    """Lower case, no punctuation, `are` as `is`, `have` as `has`, and the leading verb without
    its third-person ending (`focuses on` and `focus on` read the same)."""
    text = _NOT_WORD.sub(" ", unicodedata.normalize("NFKC", action).casefold())
    words = text.replace("_", " ").split()
    if not words:
        return ""
    head = words[0]
    if head == "are":
        head = "is"
    elif head in ("have", "has"):
        head = "has"
    elif head != "is":
        head = _verb_stem(head)
    return " ".join([head, *words[1:]])


def action_matches(predicted: str, accepted: list[str]) -> bool:
    got = normalise_action(predicted)
    for want in (normalise_action(a) for a in accepted):
        if got == want or any(got in g and want in g for g in _synonym_groups()):
            return True
    return False


def grounded(label: str, source_text: str) -> bool:
    """Whether `label` occurs in `source_text` as whole words, both normalised word by word
    (NFKC, case folded, singular)."""
    wanted = [singular(w) for w in _words(label)]
    if not wanted:
        return False
    words = [singular(w) for w in _words(source_text)]
    n = len(wanted)
    return any(words[i : i + n] == wanted for i in range(len(words) - n + 1))


def score_case(
    case: TeachCase,
    concepts: list[PredictedConcept],
    relations: list[PredictedRelation],
    source_text: str,
) -> CaseScore:
    """The case's score; the case must carry expectations."""
    if case.expected is None:
        raise ValueError(f"{case.id} has no expectations to score against")
    canon = _Canon(case)
    score = CaseScore(case_id=case.id, kind=case.kind)
    expected = {canon.of(e.label): e for e in case.expected.concepts}
    accepted = _accepted_parents(canon, case)
    groundable = {
        n
        for n, e in expected.items()
        if any(grounded(label, source_text) for label in [e.label, *e.aliases])
    }
    score.concepts_expected = len(expected)
    score.concepts_groundable = len(groundable)
    score.concepts_predicted = len(concepts)
    score.relations_expected = len(case.expected.relations)
    score.relations_predicted = len(relations)

    satisfying = _score_relations(case.expected.relations, concepts, relations, canon, score)

    matched: dict[str, PredictedConcept] = {}
    counted: list[str] = []
    for i, p in enumerate(concepts):
        n = canon.of(p.label)
        if n in expected and n not in matched:
            matched[n] = p
            counted.append(n)
        elif i in satisfying:
            continue
        elif n in canon.optional and n not in matched:
            score.optional_drafted.append(p.label)
        elif n in canon.existing or n in matched:
            score.invented.append(p.label)
            score.duplicates.append(p.label)
            counted.append(n)
        else:
            score.invented.append(p.label)
            counted.append(n)

    drafted = _drafted_parents(canon, case, concepts)
    expected_level = _levels(canon, accepted)
    drafted_level = _levels(canon, {k: {v} for k, v in drafted.items()})
    right_path: set[str] = set()
    for n, e in expected.items():
        p = matched.get(n)
        if p is None:
            score.missed.append(e.label)
            continue
        if canon.of(p.parent) in accepted[n]:
            score.parent_correct += 1
            if drafted_level(n) == expected_level(n):
                score.parent_at_depth += 1
            else:
                score.wrong_depth.append(
                    f"{e.label}: level {drafted_level(n)}, want {expected_level(n)}"
                )
        else:
            score.wrong_parent.append(f"{e.label}: got {p.parent}, want {' | '.join(e.parent)}")
        if action_matches(p.action, e.action):
            score.action_correct += 1
        else:
            score.wrong_action.append(f"{e.label}: got {p.action}, want {' | '.join(e.action)}")
        if _path_ok(canon, n, drafted, accepted):
            right_path.add(n)
        else:
            chain = " > ".join(reversed(_chain(canon, n, drafted)))
            score.wrong_path.append(f"{e.label}: got {chain}")
    score.path_correct = len(right_path)
    score.missing_branches = _missing_branches(canon, expected, accepted, set(matched))

    score.concepts_matched = len(matched)
    score.matched_groundable = len(groundable & set(matched))
    score.concept_precision = _ratio(len(matched), len(matched) + len(score.invented))
    score.concept_recall = _ratio(len(matched), len(expected))
    score.concept_f1 = f1(score.concept_precision, score.concept_recall)
    score.grounding_ceiling = _ratio(len(groundable), len(expected))
    score.concept_recall_groundable = _ratio(score.matched_groundable, len(groundable))
    score.concept_f1_groundable = f1(score.concept_precision, score.concept_recall_groundable)

    for n in expected:
        level = score.levels.setdefault(expected_level(n), LevelScore())
        level.expected += 1
        level.groundable += n in groundable
        level.correct += n in right_path
        level.correct_groundable += n in right_path and n in groundable
    for n in counted:
        score.levels.setdefault(drafted_level(n), LevelScore()).predicted += 1
    score.levels = dict(sorted(score.levels.items()))
    score.depth_expected = max((expected_level(n) for n in expected), default=0)
    score.depth_achieved = max((drafted_level(n) for n in matched), default=0)
    return score


def drafted_depth(case: TeachCase, concepts: list[PredictedConcept]) -> int:
    """The deepest level the drafts reach, for a case with no expectations."""
    canon = _Canon(case)
    drafted = _drafted_parents(canon, case, concepts)
    level = _levels(canon, {k: {v} for k, v in drafted.items()})
    return max((level(canon.of(p.label)) for p in concepts), default=0)


def f1(precision: float, recall: float) -> float:
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


class _Canon:
    """Canonical normalised labels of a case: every alias maps to its concept's label."""

    def __init__(self, case: TeachCase) -> None:
        self.root = normalise_label(case.company)
        self.existing = {normalise_label(c.label) for c in case.existing} | {self.root}
        self.optional = {normalise_label(o) for o in case.optional}
        self._alias: dict[str, str] = {}
        for e in case.expected.concepts if case.expected else []:
            n = normalise_label(e.label)
            for alias in e.aliases:
                self._alias.setdefault(normalise_label(alias), n)

    def of(self, label: str) -> str:
        n = normalise_label(label)
        return self._alias.get(n, n)


def _accepted_parents(canon: _Canon, case: TeachCase) -> dict[str, set[str]]:
    accepted = {canon.of(c.label): {canon.of(c.parent)} for c in case.existing}
    for e in case.expected.concepts if case.expected else []:
        accepted.setdefault(canon.of(e.label), set()).update(canon.of(p) for p in e.parent)
    return accepted


def _drafted_parents(
    canon: _Canon, case: TeachCase, concepts: list[PredictedConcept]
) -> dict[str, str]:
    """Each label's parent in the drafted tree: existing concepts keep theirs, a drafted label
    takes the parent of its first draft."""
    parents = {canon.of(c.label): canon.of(c.parent) for c in case.existing}
    for p in concepts:
        parents.setdefault(canon.of(p.label), canon.of(p.parent))
    return parents


def _levels(canon: _Canon, parents: dict[str, set[str]]) -> Callable[[str], int]:
    """A function giving a label's shortest distance to the root through `parents`; a parent
    the tree does not know counts as the root, a cycle as unreachable from it."""
    memo: dict[str, int] = {canon.root: 0}
    visiting: set[str] = set()

    def level(n: str) -> int:
        if n in memo:
            return memo[n]
        if n in visiting:
            return _UNREACHABLE
        visiting.add(n)
        ups = parents.get(n, set())
        best = min((level(p) for p in ups if p in parents or p == canon.root), default=None)
        if best is None:
            best = 0
        visiting.discard(n)
        memo[n] = best + 1 if best < _UNREACHABLE else _UNREACHABLE
        return memo[n]

    return level


def _path_ok(canon: _Canon, n: str, drafted: dict[str, str], accepted: dict[str, set[str]]) -> bool:
    node, seen = n, {n}
    while node != canon.root:
        parent = drafted.get(node)
        if parent is None or parent not in accepted.get(node, set()) or parent in seen:
            return False
        seen.add(parent)
        node = parent
    return True


def _chain(canon: _Canon, n: str, drafted: dict[str, str]) -> list[str]:
    chain, node = [n], n
    while node != canon.root and node in drafted and drafted[node] not in chain:
        node = drafted[node]
        chain.append(node)
    return chain


def _missing_branches(
    canon: _Canon,
    expected: dict[str, ExpectedConcept],
    accepted: dict[str, set[str]],
    matched: set[str],
) -> list[str]:
    missed = set(expected) - matched
    children: dict[str, set[str]] = {}
    for n in expected:
        for p in accepted[n]:
            children.setdefault(p, set()).add(n)
    tops = [n for n in missed if not accepted[n] & missed]
    out: list[str] = []
    for top in sorted(tops, key=lambda n: expected[n].label):
        size, stack, seen = 0, [top], set()
        while stack:
            node = stack.pop()
            if node in seen or node not in missed:
                continue
            seen.add(node)
            size += 1
            stack.extend(children.get(node, ()))
        out.append(f"{expected[top].label} ({size} nodes)")
    return out


def _score_relations(
    expected: list[ExpectedRelation],
    concepts: list[PredictedConcept],
    relations: list[PredictedRelation],
    canon: _Canon,
    score: CaseScore,
) -> set[int]:
    """Scores relations into `score`; returns the indexes of drafted concepts that stand for an
    expected relation."""
    open_: list[ExpectedRelation] = list(expected)
    for r in relations:
        src, tgt = canon.of(r.source), canon.of(r.target)
        found = _take(open_, canon, src, tgt)
        if found is None:
            score.invented_relations.append(f"{r.source} {r.action} {r.target}")
            continue
        score.relations_matched += 1
        if _relation_action_ok(found, canon, src, r.action):
            score.relation_action_correct += 1
    satisfying: set[int] = set()
    for i, p in enumerate(concepts):
        if not open_:
            break
        parent, label = canon.of(p.parent), canon.of(p.label)
        src, tgt = (label, parent) if p.reverse else (parent, label)
        found = _take(open_, canon, src, tgt)
        if found is None:
            continue
        satisfying.add(i)
        score.relations_matched += 1
        if _relation_action_ok(found, canon, src, p.action):
            score.relation_action_correct += 1
    score.missed_relations = [f"{e.source} {e.action[0]} {e.target}" for e in open_]
    predicted = len(relations) + len(satisfying)
    score.relation_precision = _ratio(score.relations_matched, predicted)
    score.relation_recall = _ratio(score.relations_matched, len(expected))
    return satisfying


def _take(open_: list[ExpectedRelation], canon: _Canon, a: str, b: str) -> ExpectedRelation | None:
    for e in open_:
        if {canon.of(e.source), canon.of(e.target)} == {a, b}:
            open_.remove(e)
            return e
    return None


def _relation_action_ok(e: ExpectedRelation, canon: _Canon, source: str, action: str) -> bool:
    if canon.of(e.source) == source:
        return action_matches(action, e.action)
    return bool(e.inverse) and action_matches(action, e.inverse)


def _words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKC", text).casefold().replace("&", " and ")
    return _WORD.findall(folded.replace("_", " "))


def _ratio(num: int, den: int) -> float:
    return 1.0 if den == 0 else num / den


def _verb_stem(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    for ending in ("ches", "shes", "sses", "xes", "zes", "ses"):
        if word.endswith(ending):
            return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


@cache
def _synonym_groups() -> tuple[frozenset[str], ...]:
    return tuple(frozenset(normalise_action(a) for a in group) for group in _SYNONYM_GROUPS_RAW)
