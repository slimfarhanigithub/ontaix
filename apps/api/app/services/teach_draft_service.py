"""Intents to proposal drafts: the grammar's mapping table, shared by grammar and model intents.

A `rel` intent: an existing subject and a new object give a concept born from the subject; a
new subject and an existing object give a concept born from the object with `reverse`; two
existing concepts give a relation; two new concepts give a concept born from the company root
with `has` and a second one born from it by label. A `spec` intent (subject the child, object
the parent): new child and existing parent give a spec draft; existing child and existing
parent give an `is a` relation; existing child and new parent give the parent born from the
child with `is a kind of` and `reverse`; two new concepts give the parent born from the root
with `has` and the child specialised from it by label.

Every intent is planned first and kept only while the result stays within 60 intents and 60
drafts; the rest are dropped together and reported as one `too_many_drafts` phrase.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.models.api.teach import DraftNote, Intent, UnresolvedPhrase
from app.models.storage.concept import Concept
from app.services.ontology_view_service import OntologyView
from app.utilities.action_text import normalise_action
from app.utilities.teach_parser import content_words, singular, title, understand

logger = logging.getLogger(__name__)

# Caps of one result: a typed or document sentence, and a whole speech transcript.
MAX_INTENTS = 60
MAX_UNRESOLVED = 20
MAX_TRANSCRIPT_INTENTS = 150
MAX_TRANSCRIPT_UNRESOLVED = 40
MAX_PHRASE_CHARS = 400
DEFAULT_DOMAIN = "production"
RULES_NOTE = DraftNote(extractor="rules", confidence=1)


@dataclass(frozen=True)
class End:
    """One end of an intent: an existing concept, or a new label."""

    concept: Concept | None
    label: str
    text: str
    # The model named this end by a new label (it may still resolve to an existing concept).
    cited_new: bool = False


@dataclass
class PlannedIntent:
    intent: Intent
    drafts: list[dict[str, Any]]
    statements: list[str]
    note: DraftNote
    identity: tuple[str, str, str]
    span: str | None = None
    concept_ids: list[uuid.UUID] = field(default_factory=list)
    segment: int = 0


@dataclass
class Assembled:
    kept: list[PlannedIntent]
    intents: list[Intent]
    drafts: list[dict[str, Any]]
    notes: list[DraftNote]
    statements: list[str]
    unresolved: list[UnresolvedPhrase]
    concept_ids: list[uuid.UUID]


class Drafter:
    """Plans the drafts of one intent at a time for one company of one view."""

    def __init__(
        self,
        view: OntologyView,
        company_id: uuid.UUID,
        root: Concept,
        dom_key: str | None,
        draft_extras: dict[str, Any],
    ) -> None:
        self.view = view
        self.company_id = company_id
        self.root = root
        self.dom_key = dom_key
        self.extras = draft_extras
        # New concepts earlier model intents of this result introduce: label to domain key.
        self.introduced: dict[str, tuple[str, str]] = {}
        self.mine = sorted(
            (c for c in view.live_concepts() if c.company_id == company_id),
            key=lambda c: (c.born_at, str(c.id)),
        )

    def resolve(self, np: str) -> Concept | None:
        """The company's concept a noun phrase names, exactly or by singular and plural."""
        if not np:
            return None
        lower = np.lower()
        wanted = title(np).lower()
        return next((n for n in self.mine if n.label.lower() == wanted), None) or next(
            (
                n
                for n in self.mine
                if n.label.lower() == singular(lower) or singular(n.label.lower()) == lower
            ),
            None,
        )

    def by_label(self, label: str) -> Concept | None:
        wanted = label.lower()
        return next((n for n in self.mine if n.label.lower() == wanted), None)

    def key(self, fallback: str | None) -> str:
        return self.dom_key or fallback or DEFAULT_DOMAIN

    def spec(
        self,
        child: End,
        parent: End,
        rule: str | None,
        note: DraftNote,
        domain_hint: str | None = None,
        intent_rule: str | None = None,
    ) -> PlannedIntent:
        company = str(self.company_id)
        drafts: list[dict[str, Any]] = []
        made: list[str] = []
        p, c = parent.concept, child.concept
        intent = Intent(
            kind="spec",
            subject=child.text,
            object=parent.text,
            rule=intent_rule if intent_rule is not None else rule,
            subject_resolved=c.id if c else None,
            object_resolved=p.id if p else None,
        )
        if p and not c:
            plus = ", plus the rule you gave" if rule else ""
            drafts.append(
                self.draft(
                    type="spec",
                    companyId=company,
                    parentId=str(p.id),
                    label=child.label,
                    rule=rule or "",
                    domainKey=self.key(domain_hint or self.view.domain_key(p)),
                    caption=(
                        f"{p.label} divides: {child.label} inherits everything {p.label} is{plus}."
                    ),
                )
            )
            made.append(f"{child.label} is a {p.label}")
        elif p and c:
            drafts.append(
                self.draft(
                    type="relation",
                    aId=str(c.id),
                    bId=str(p.id),
                    action="is a",
                    caption=f"{c.label} is a {p.label}: it inherits everything {p.label} is.",
                )
            )
            made.append(f"{c.label} is a {p.label}")
        elif c:
            drafts.append(
                self.draft(
                    type="concept",
                    companyId=company,
                    parentId=str(c.id),
                    label=parent.label,
                    domainKey=self.key(domain_hint or self.view.domain_key(c)),
                    action="is a kind of",
                    reverse=True,
                )
            )
            made.append(f"{c.label} is a kind of {parent.label} (new)")
        else:
            drafts.append(
                self.draft(
                    type="concept",
                    companyId=company,
                    parentId=str(self.root.id),
                    label=parent.label,
                    domainKey=self.key(domain_hint),
                    action="has",
                )
            )
            drafts.append(
                self.draft(
                    type="spec",
                    companyId=company,
                    parentLabel=parent.label,
                    label=child.label,
                    rule=rule or "",
                    domainKey=self.key(domain_hint),
                )
            )
            made.append(f"{child.label} is a {parent.label} (both new)")
        return PlannedIntent(
            intent, drafts, made, note, _identity(child, "is a", parent), None, _ids(child, parent)
        )

    def rel(
        self,
        a_end: End,
        b_end: End,
        pred: str,
        note: DraftNote,
        domain_hint: str | None = None,
    ) -> PlannedIntent:
        company = str(self.company_id)
        drafts: list[dict[str, Any]] = []
        made: list[str] = []
        a, b = a_end.concept, b_end.concept
        intent = Intent(
            kind="rel",
            subject=a_end.text,
            predicate=pred,
            object=b_end.text,
            rule="llm" if note.extractor == "llm" else None,
            subject_resolved=a.id if a else None,
            object_resolved=b.id if b else None,
        )
        if a and b:
            if a.id != b.id:
                drafts.append(
                    self.draft(
                        type="relation",
                        aId=str(a.id),
                        bId=str(b.id),
                        action=pred,
                        caption=(
                            f"{a.label} {pred} {b.label}: from {a.label} to {b.label}, "
                            "the action on the line."
                        ),
                    )
                )
                made.append(f"{a.label} {pred} {b.label}")
        elif a:
            drafts.append(
                self.draft(
                    type="concept",
                    companyId=company,
                    parentId=str(a.id),
                    label=b_end.label,
                    domainKey=self.key(domain_hint or self.view.domain_key(a)),
                    action=pred,
                    caption=f"{b_end.label} is kept. {a.label} {pred} {b_end.label}.",
                )
            )
            made.append(f"{a.label} {pred} {b_end.label} (new)")
        elif b:
            drafts.append(
                self.draft(
                    type="concept",
                    companyId=company,
                    parentId=str(b.id),
                    label=a_end.label,
                    domainKey=self.key(domain_hint or self.view.domain_key(b)),
                    action=pred,
                    reverse=True,
                    caption=f"{a_end.label} is kept. {a_end.label} {pred} {b.label}.",
                )
            )
            made.append(f"{a_end.label} (new) {pred} {b.label}")
        else:
            drafts.append(
                self.draft(
                    type="concept",
                    companyId=company,
                    parentId=str(self.root.id),
                    label=a_end.label,
                    domainKey=self.key(domain_hint),
                    action="has",
                )
            )
            drafts.append(
                self.draft(
                    type="concept",
                    companyId=company,
                    parentLabel=a_end.label,
                    label=b_end.label,
                    domainKey=self.key(domain_hint),
                    action=pred,
                )
            )
            made.append(f"{a_end.label} {pred} {b_end.label} (both new)")
        return PlannedIntent(
            intent,
            drafts,
            made,
            note,
            _identity(a_end, normalise_action(pred), b_end),
            None,
            _ids(a_end, b_end),
        )

    def model_rel(
        self, a_end: End, b_end: End, pred: str, note: DraftNote, domain_hint: str | None
    ) -> PlannedIntent:
        """A model `rel` intent; an end naming a concept an earlier intent of the same answer
        introduces is cited by label instead of being born a second time."""
        a_in, b_in = self._introduced(a_end), self._introduced(b_end)
        if a_in is None and b_in is None:
            planned = self.rel(a_end, b_end, pred, note, domain_hint=domain_hint)
        else:
            planned = self._rel_by_label(a_end, b_end, a_in, b_in, pred, note, domain_hint)
        self._register(planned)
        return planned

    def model_spec(
        self, child: End, parent: End, rule: str | None, note: DraftNote, domain_hint: str | None
    ) -> PlannedIntent:
        """A model `spec` intent; a parent an earlier intent introduces is cited by label."""
        p_in = self._introduced(parent)
        if p_in is not None and child.concept is None and self._introduced(child) is None:
            label, domain = p_in
            intent = Intent(
                kind="spec",
                subject=child.text,
                object=parent.text,
                rule="llm",
                subject_resolved=None,
                object_resolved=None,
            )
            draft = self.draft(
                type="spec",
                companyId=str(self.company_id),
                parentLabel=label,
                label=child.label,
                rule=rule or "",
                domainKey=self.key(domain_hint or domain),
            )
            planned = PlannedIntent(
                intent,
                [draft],
                [f"{child.label} is a {label}"],
                note,
                _identity(child, "is a", parent),
            )
        else:
            planned = self.spec(
                child, parent, rule, note, domain_hint=domain_hint, intent_rule="llm"
            )
        self._register(planned)
        return planned

    def _rel_by_label(
        self,
        a_end: End,
        b_end: End,
        a_in: tuple[str, str] | None,
        b_in: tuple[str, str] | None,
        pred: str,
        note: DraftNote,
        domain_hint: str | None,
    ) -> PlannedIntent:
        company = str(self.company_id)
        a, b = a_end.concept, b_end.concept
        intent = Intent(
            kind="rel",
            subject=a_end.text,
            predicate=pred,
            object=b_end.text,
            rule="llm",
            subject_resolved=a.id if a else None,
            object_resolved=b.id if b else None,
        )
        a_label = a_in[0] if a_in else a_end.label
        b_label = b_in[0] if b_in else b_end.label
        if a_in and b is None and b_in is None:
            drafts = [
                self.draft(
                    type="concept",
                    companyId=company,
                    parentLabel=a_label,
                    label=b_end.label,
                    domainKey=self.key(domain_hint or a_in[1]),
                    action=pred,
                    caption=f"{b_end.label} is kept. {a_label} {pred} {b_end.label}.",
                )
            ]
            made = f"{a_label} {pred} {b_end.label} (new)"
        elif b_in and a is None and a_in is None:
            drafts = [
                self.draft(
                    type="concept",
                    companyId=company,
                    parentLabel=b_label,
                    label=a_end.label,
                    domainKey=self.key(domain_hint or b_in[1]),
                    action=pred,
                    reverse=True,
                    caption=f"{a_end.label} is kept. {a_end.label} {pred} {b_label}.",
                )
            ]
            made = f"{a_end.label} (new) {pred} {b_label}"
        else:
            ends: dict[str, Any] = {}
            ends.update({"aId": str(a.id)} if a else {"aLabel": a_label})
            ends.update({"bId": str(b.id)} if b else {"bLabel": b_label})
            drafts = [self.draft(type="relation", companyId=company, action=pred, **ends)]
            made = f"{a.label if a else a_label} {pred} {b.label if b else b_label}"
        return PlannedIntent(
            intent,
            drafts,
            [made],
            note,
            _identity(a_end, normalise_action(pred), b_end),
            None,
            _ids(a_end, b_end),
        )

    def _introduced(self, end: End) -> tuple[str, str] | None:
        if end.concept is not None:
            return None
        return self.introduced.get(end.label.lower())

    def _register(self, planned: PlannedIntent) -> None:
        for d in planned.drafts:
            if d.get("type") in ("concept", "spec"):
                self.introduced.setdefault(d["label"].lower(), (d["label"], d["domainKey"]))

    def draft(self, **fields: Any) -> dict[str, Any]:
        return {**self.extras, **fields}


NOT_UNDERSTOOD = (
    "Try “<subject> <action> <object>”, “A is a B”, or “A that … is a B”. "
    "Start with “In quality, …” to choose the domain product."
)


@dataclass
class GrammarPlan:
    planned: list[PlannedIntent]
    outcome: str
    caption: str
    # The part of a transcript past the segments the degraded split keeps, if any.
    beyond: str | None = None


def plan_grammar(drafter: Drafter, text: str) -> GrammarPlan:
    """The grammar's intents for `text` (after its domain prefix), as the reference reads it."""
    planned: list[PlannedIntent] = []
    for it in understand(text):
        if it.kind == "spec":
            child = End(drafter.resolve(it.subj), title(it.subj), it.subj)
            parent = End(drafter.resolve(it.obj), title(it.obj), it.obj)
            planned.append(drafter.spec(child, parent, it.rule, RULES_NOTE))
            continue
        a = End(drafter.resolve(it.subj), title(it.subj), it.subj)
        b = End(drafter.resolve(it.obj), title(it.obj), it.obj)
        planned.append(drafter.rel(a, b, it.pred or "relates to", RULES_NOTE))
    statements = [s for p in planned for s in p.statements]
    if statements:
        caption = " · ".join(statements) + ". Waiting for your approval on the right."
        return GrammarPlan(planned, "understood", caption)

    # Nothing parsed: propose the unknown words mentioned next to a concept the sentence names.
    words = content_words(text)
    named = [n for n in drafter.mine if n.label.lower() in words]
    fresh = [w for w in dict.fromkeys(words) if not drafter.by_label(title(w))][:3]
    if not fresh or not named:
        return GrammarPlan(planned, "not_understood", NOT_UNDERSTOOD)
    host = named[0]
    for w in fresh:
        draft = drafter.draft(
            type="concept",
            companyId=str(drafter.company_id),
            parentId=str(host.id),
            label=title(w),
            domainKey=drafter.key(drafter.view.domain_key(host)),
            action="relates to",
            caption=f"{title(w)} is kept.",
        )
        intent = Intent(
            kind="rel",
            subject=host.label.lower(),
            predicate="relates to",
            object=w,
            subject_resolved=host.id,
            object_resolved=None,
        )
        planned.append(
            PlannedIntent(
                intent,
                [draft],
                [],
                RULES_NOTE,
                (str(host.id), "relates to", title(w).lower()),
                None,
                [host.id],
            )
        )
    names = ", ".join(title(w) for w in fresh)
    caption = (
        f"No action found; {names} proposed from {host.label} with “relates to”. "
        "Click the line to give it the right action."
    )
    return GrammarPlan(planned, "partly_understood", caption)


def assemble(planned: list[PlannedIntent], sentence: str, cap: int = MAX_INTENTS) -> Assembled:
    """Keeps planned intents in order while at most `cap` intents and `cap` drafts are kept
    (60, or 150 for a speech transcript)."""
    out = Assembled([], [], [], [], [], [], [])
    dropped: list[PlannedIntent] = []
    for p in planned:
        full = len(out.intents) >= cap or len(out.drafts) + len(p.drafts) > cap
        if dropped or full:
            dropped.append(p)
            continue
        out.kept.append(p)
        out.intents.append(p.intent)
        out.drafts.extend(p.drafts)
        out.notes.extend([p.note] * len(p.drafts))
        out.statements.extend(p.statements)
        out.concept_ids.extend(i for i in p.concept_ids if i not in out.concept_ids)
    if dropped:
        out.unresolved.append(
            UnresolvedPhrase(text=phrase_in(sentence, dropped[0].span), reason="too_many_drafts")
        )
    return out


def phrase_in(sentence: str, phrase: str | None) -> str:
    """The part of `sentence` matching `phrase` (case-insensitive), else the whole sentence."""
    if phrase:
        at = sentence.lower().find(phrase.strip().lower())
        if at >= 0 and phrase.strip():
            return sentence[at : at + len(phrase.strip())][:MAX_PHRASE_CHARS]
    return sentence[:MAX_PHRASE_CHARS]


def add_unresolved(
    target: list[UnresolvedPhrase], phrase: UnresolvedPhrase, cap: int = MAX_UNRESOLVED
) -> None:
    """Appends a phrase once, keeping at most `cap` (20, or 40 for a speech transcript)."""
    if len(target) >= cap:
        return
    if any(u.text == phrase.text and u.reason == phrase.reason for u in target):
        return
    target.append(phrase)


def new_labels(drafts: list[dict[str, Any]]) -> list[str]:
    """The labels of the concepts the drafts introduce, in order, once each."""
    labels: list[str] = []
    for d in drafts:
        if d.get("type") in ("concept", "spec") and d["label"] not in labels:
            labels.append(d["label"])
    return labels


def _identity(a: End, action: str, b: End) -> tuple[str, str, str]:
    def side(e: End) -> str:
        return str(e.concept.id) if e.concept else e.label.lower()

    return side(a), action, side(b)


def _ids(*ends: End) -> list[uuid.UUID]:
    return [e.concept.id for e in ends if e.concept is not None]
