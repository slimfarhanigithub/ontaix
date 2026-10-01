"""The deterministic mapping of a parsed ontology or hierarchy onto one company's draft tree.

Items keep file order after a stable sort by source (hierarchy tables keep row order), so the
same file gives the same tree. Each item gets a label chosen by language preference and checked
against the label rules; a label already in the company reuses that concept, and a second item
with the same label is dropped. An item hangs under its first named parent in label order -
as a specialisation for `subClassOf` and `is_a`, as a concept born with `includes` for
`skos:broader` and hierarchy rows, with `has instance` for an individual - and further named
parents become relations. Cycles are broken at the first repeated item. Relations come from
object properties with a named domain and range, from some and all restrictions and from OBO
relationships, their verb taken from the property. Everything left out is reported with its
source and reason. Drafts come parents first, then relations; above `max_nodes` drafts the
whole import is refused.

A file in the Ontaix vocabulary, as an Ontaix OWL export is, maps back into the model it came
from: the company root is not drafted, its children hang under the import's parent; a class
hangs under its `ox:bornFrom` parent - a specialisation when it is also `rdfs:subClassOf` it,
else born with its `ox:birthAction`, reversed with `ox:birthReverse` - and its further parents
become relations; `ox:domain` sets its domain when the company has it (else the parent's, with
`unknown_domain`); a restriction that repeats a birth relation is not drafted twice; object
property domains and ranges add nothing, since the restrictions carry every relation; and each
taught attribute becomes an attribute draft after the relations.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

from app.models.ontology_import.parsed_ontology import (
    LABEL_PROPERTIES,
    LabelLiteral,
    OntologyItem,
    ParsedOntology,
    SkipReason,
)
from app.utilities.action_text import has_refused_character, normalise_action
from app.utilities.document_errors import DocumentTooLargeError
from app.utilities.teach_parser import singular, title

MAX_LABEL_CHARS = 120
MAX_VERB_CHARS = 60
MAX_SOURCE_CHARS = 400
MAX_SKIPPED = 100_000
MAX_RULE_CHARS = 200
MAX_ATTRIBUTE_NAME_CHARS = 80
MAX_ATTRIBUTE_VALUE_CHARS = 200
TAUGHT_TYPES = ("text", "number", "date")
DEFAULT_DOMAIN = "production"
INCLUDES = "includes"
HAS_INSTANCE = "has instance"
IS_A = "is a"
FORBIDDEN_ACTIONS = ("is a", "equivalent to")

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SEPARATORS = re.compile(r"[_\s]+")
_LINE_SEPARATORS = ("\u2028", "\u2029", "\u0085")


@dataclass(frozen=True)
class ExistingConcept:
    """A live or pending concept of the target company."""

    id: uuid.UUID
    label: str
    parent_id: uuid.UUID | None
    domain_key: str | None


@dataclass(frozen=True)
class MappingTarget:
    """Where the tree goes and how it is chosen: the company, the concept the top items hang
    under, the company's domain keys, and the caller's options."""

    company_id: uuid.UUID
    parent_id: uuid.UUID
    parent_domain_key: str | None
    domain_keys: frozenset[str]
    domain_key: str | None
    languages: tuple[str, ...]
    individuals: str
    max_nodes: int


@dataclass
class MappedTree:
    """Drafts in the wire shape of `ProposalDraft`, one note per draft, and the skipped items."""

    drafts: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)


def map_ontology(
    parsed: ParsedOntology,
    target: MappingTarget,
    existing: list[ExistingConcept],
    existing_relations: set[tuple[uuid.UUID, uuid.UUID, str]],
) -> MappedTree:
    return _Mapper(parsed, target, existing, existing_relations).run()


def choose_label(
    labels: dict[str, list[LabelLiteral]], fallback: str, languages: tuple[str, ...]
) -> tuple[str, str | None]:
    """The first non-empty candidate of the label properties in order, each chosen by language,
    else the fallback name split into words; with the chosen literal's language tag."""
    for prop in LABEL_PROPERTIES:
        candidates = [lit for lit in labels.get(prop, []) if lit.text.strip()]
        if candidates:
            chosen = _by_language(candidates, languages)
            return chosen.text, chosen.language
    return words_of(fallback), None


def words_of(name: str) -> str:
    """A local name as words: percent-decoded, split at camel case, underscores and spaces."""
    return " ".join(_SEPARATORS.sub(" ", _CAMEL.sub(" ", unquote(name))).split())


def checked_label(text: str) -> str | None:
    """The label after NFKC and the casing rule, when it passes every label rule."""
    label = title(unicodedata.normalize("NFKC", text).strip())
    if not 0 < len(label) <= MAX_LABEL_CHARS or has_refused_character(label):
        return None
    return label


def verb_of(text: str) -> str:
    """A relation verb: words, lower-cased, whitespace collapsed, normalised as every action,
    at most 60 characters."""
    return normalise_action(words_of(text).lower())[:MAX_VERB_CHARS].strip()


def safe_source(source: str) -> str:
    """The source with Cf, control, bidirectional and line-separator characters percent-encoded
    as UTF-8, at most 400 characters."""
    out = []
    for char in source:
        if unicodedata.category(char) in ("Cc", "Cf") or char in _LINE_SEPARATORS:
            out.append("".join(f"%{b:02X}" for b in char.encode("utf-8")))
        else:
            out.append(char)
    return "".join(out)[:MAX_SOURCE_CHARS]


def _by_language(candidates: list[LabelLiteral], languages: tuple[str, ...]) -> LabelLiteral:
    for tag in languages:
        wanted = tag.lower()
        exact = [c for c in candidates if c.language == wanted]
        if exact:
            return exact[0]
        primary = wanted.split("-")[0]
        near = [c for c in candidates if c.language and c.language.split("-")[0] == primary]
        if near:
            return near[0]
    untagged = [c for c in candidates if c.language is None]
    if untagged:
        return untagged[0]
    return sorted(candidates, key=lambda c: (c.language or "", c.text))[0]


@dataclass
class _Node:
    item: OntologyItem
    label: str
    language: str | None
    parent: str | None = None
    parent_kind: str = INCLUDES
    extra_parents: list[tuple[str, str]] = field(default_factory=list)
    existing: ExistingConcept | None = None
    draft_index: int | None = None
    domain: str | None = None
    depth: int = 0


class _Mapper:
    def __init__(
        self,
        parsed: ParsedOntology,
        target: MappingTarget,
        existing: list[ExistingConcept],
        existing_relations: set[tuple[uuid.UUID, uuid.UUID, str]],
    ) -> None:
        self.parsed = parsed
        self.target = target
        self.existing = existing
        self.existing_relations = existing_relations
        self.existing_by_label = {c.label.lower(): c for c in existing}
        self.tree = MappedTree()
        self.nodes: dict[str, _Node] = {}
        # A dropped duplicate's source to the source of the item that kept the label.
        self.alias: dict[str, str] = {}
        self.relation_keys: set[tuple[str, str, str]] = set()
        # The company roots of an Ontaix export: never drafted, they stand for the import parent.
        self.roots: set[str] = set()
        # `(subject, object, action)` of each birth read from an Ontaix export.
        self.birth_keys: set[tuple[str, str, str]] = set()

    def run(self) -> MappedTree:
        for entry in self.parsed.skipped:
            self._skip(entry.source, entry.reason, entry.label)
        self._choose_labels()
        self._choose_parents()
        self._break_cycles()
        self._reuse_existing()
        done: set[str] = set()
        for source in self.nodes:
            # Ancestors first, walked up without recursion: paths are as deep as the file.
            chain: list[str] = []
            current: str | None = source
            while current is not None and current not in done:
                chain.append(current)
                current = self.nodes[current].parent
            for pending in reversed(chain):
                self._emit_concept(pending)
                done.add(pending)
        self._relations()
        if self.parsed.ontaix:
            self._attributes()
        if len(self.tree.drafts) > self.target.max_nodes:
            raise DocumentTooLargeError(
                f"the file maps to more than {self.target.max_nodes} proposals"
            )
        return self.tree

    def _choose_labels(self) -> None:
        items = (
            self.parsed.items
            if self.parsed.table
            else sorted(self.parsed.items, key=lambda i: i.source)
        )
        kept_by_label: dict[str, str] = {}
        for item in items:
            if self.parsed.ontaix and item.root and not item.individual:
                self.roots.add(item.source)
                continue
            if item.individual and self.target.individuals != "as_concepts":
                self._skip(item.source, "individual_skipped")
                continue
            text, language = choose_label(item.labels, item.local_name, self.target.languages)
            label = checked_label(text)
            if label is None:
                self._skip(item.source, "invalid_label")
                continue
            key = label.lower()
            if key in kept_by_label:
                self.alias[item.source] = kept_by_label[key]
                self._skip(item.source, "duplicate_label", label)
                continue
            kept_by_label[key] = item.source
            self.nodes[item.source] = _Node(item, label, language)

    def _choose_parents(self) -> None:
        for node in self.nodes.values():
            named: list[tuple[str, str]] = []
            for parent, kind in node.item.parents:
                resolved = self.alias.get(parent, parent)
                if resolved in self.nodes and resolved != node.item.source:
                    if all(p != resolved for p, _ in named):
                        named.append((resolved, kind))
            named.sort(key=lambda p: (self.nodes[p[0]].label.lower(), p[0]))
            if node.item.born_from is not None:
                self._born_from(node, named)
                continue
            if named:
                node.parent, node.parent_kind = named[0]
                node.extra_parents = named[1:]
            elif node.item.individual:
                node.parent_kind = "instance"

    def _born_from(self, node: _Node, named: list[tuple[str, str]]) -> None:
        """Hang an item of an Ontaix export under its birth parent; its other parents become
        relations. A birth parent outside the file, or the company root, puts it at the top."""
        item = node.item
        born = item.born_from or ""
        resolved = self.alias.get(born, born)
        spec = (born, "spec") in item.parents
        node.extra_parents = [(p, k) for p, k in named if p != resolved]
        if resolved in self.nodes and resolved != item.source:
            node.parent = resolved
            node.parent_kind = "spec" if spec else INCLUDES
        if not spec:
            action = normalise_action(item.action or INCLUDES)[:MAX_VERB_CHARS].strip()
            ends = (item.source, born) if item.birth_reverse else (born, item.source)
            self.birth_keys.add((*ends, action))

    def _break_cycles(self) -> None:
        done: set[str] = set()
        for source in self.nodes:
            path: list[str] = []
            on_path: set[str] = set()
            current: str | None = source
            while current is not None and current not in done:
                if current in on_path:
                    self.nodes[current].parent = None
                    self._skip(current, "cycle", self.nodes[current].label)
                    break
                path.append(current)
                on_path.add(current)
                current = self.nodes[current].parent
            done.update(path)

    def _reuse_existing(self) -> None:
        for node in self.nodes.values():
            node.existing = self._resolve(node.label)

    def _resolve(self, label: str) -> ExistingConcept | None:
        """The company's concept a label names, exactly or by singular and plural."""
        lower = label.lower()
        found = self.existing_by_label.get(lower)
        if found is not None:
            return found
        return next(
            (
                c
                for c in self.existing
                if c.label.lower() == singular(lower) or singular(c.label.lower()) == lower
            ),
            None,
        )

    def _emit_concept(self, source: str) -> None:
        """Emit the draft of one item whose parent is done, or report it reused or known."""
        node = self.nodes[source]
        parent = self.nodes[node.parent] if node.parent else None
        parent_domain = parent.domain if parent is not None else self.target.parent_domain_key
        node.depth = parent.depth + 1 if parent is not None else 1
        if node.existing is not None:
            node.domain = node.existing.domain_key or DEFAULT_DOMAIN
            expected_parent = (
                (parent.existing.id if parent.existing else None)
                if parent is not None
                else self.target.parent_id
            )
            known = expected_parent is not None and node.existing.parent_id == expected_parent
            self._skip(source, "already_known" if known else "reused_existing", node.label)
            return
        node.domain = self._domain(node, parent_domain)
        draft: dict[str, Any] = {
            "companyId": str(self.target.company_id),
            "label": node.label,
            "domainKey": node.domain,
        }
        requires: list[int] = []
        if parent is None:
            draft["parentId"] = str(self.target.parent_id)
        elif parent.existing is not None:
            draft["parentId"] = str(parent.existing.id)
        else:
            draft["parentLabel"] = parent.label
            if parent.draft_index is not None:
                requires.append(parent.draft_index)
        if node.parent_kind == "spec" and parent is not None:
            draft = {"type": "spec", **draft}
            if node.item.rule and node.item.rule.strip():
                draft["rule"] = node.item.rule.strip()[:MAX_RULE_CHARS]
        else:
            draft = {"type": "concept", **draft, "action": self._birth_action(node)}
            if node.item.birth_reverse:
                draft["reverse"] = True
        node.draft_index = len(self.tree.drafts)
        self.tree.drafts.append(draft)
        self.tree.notes.append(
            {
                "source": safe_source(source),
                "labelLanguage": node.language,
                "depth": node.depth,
                "requires": requires,
            }
        )

    def _birth_action(self, node: _Node) -> str:
        if node.parent_kind == "instance":
            return HAS_INSTANCE
        if node.item.action:
            action = normalise_action(node.item.action)[:MAX_VERB_CHARS].strip()
            if action in FORBIDDEN_ACTIONS:
                self._skip(node.item.source, "forbidden_action", node.label)
            elif action and not has_refused_character(action):
                return action
        return INCLUDES

    def _domain(self, node: _Node, parent_domain: str | None) -> str:
        keys = self.target.domain_keys
        if node.item.domain and node.item.domain in keys:
            return node.item.domain
        if node.item.domain and self.parsed.ontaix:
            self._skip(node.item.source, "unknown_domain", node.label)
        if self.target.domain_key:
            return self.target.domain_key
        if parent_domain and parent_domain in keys:
            return parent_domain
        return DEFAULT_DOMAIN

    def _relations(self) -> None:
        for node in self.nodes.values():
            for parent, kind in node.extra_parents:
                if kind == "spec":
                    self._relation(node.item.source, parent, IS_A, node.item.source)
                else:
                    action = HAS_INSTANCE if kind == "instance" else INCLUDES
                    self._relation(parent, node.item.source, action, node.item.source)
        for prop in sorted(self.parsed.properties.values(), key=lambda p: p.source):
            if self.parsed.ontaix or not prop.domains or not prop.ranges:
                continue
            verb = self._verb(prop.source)
            if verb is None:
                continue
            for domain in prop.domains:
                for rng in prop.ranges:
                    self._relation(domain, rng, verb, prop.source)
        for statement in self.parsed.statements:
            verb = self._verb(statement.property)
            if verb is None:
                continue
            if (statement.subject, statement.object, verb) in self.birth_keys:
                continue
            self._relation(statement.subject, statement.object, verb, statement.subject)

    def _verb(self, prop_source: str) -> str | None:
        prop = self.parsed.properties.get(prop_source)
        labels = prop.labels if prop else {}
        name = prop.local_name if prop else prop_source
        text, _ = choose_label(labels, name, self.target.languages)
        verb = verb_of(text)
        if verb in FORBIDDEN_ACTIONS:
            self._skip(prop_source, "forbidden_action")
            return None
        if not verb or has_refused_character(verb):
            self._skip(prop_source, "invalid_label")
            return None
        return verb

    def _relation(self, a_source: str, b_source: str, action: str, source: str) -> None:
        a = self._end(a_source)
        b = self._end(b_source)
        if a is None or b is None:
            self._skip(source, "unknown_parent")
            return
        if a is b:
            self._skip(source, "unsupported_axiom")
            return
        key = (a.item.source, b.item.source, action)
        if key in self.relation_keys:
            return
        self.relation_keys.add(key)
        if (
            a.existing
            and b.existing
            and (a.existing.id, b.existing.id, action) in (self.existing_relations)
        ):
            self._skip(source, "already_known")
            return
        draft: dict[str, Any] = {"type": "relation", "companyId": str(self.target.company_id)}
        requires: list[int] = []
        for end, node in (("a", a), ("b", b)):
            if node.item.root:
                draft[f"{end}Id"] = str(self.target.parent_id)
            elif node.existing is not None:
                draft[f"{end}Id"] = str(node.existing.id)
            else:
                draft[f"{end}Label"] = node.label
                if node.draft_index is not None:
                    requires.append(node.draft_index)
        draft["action"] = action
        self.tree.drafts.append(draft)
        self.tree.notes.append(
            {
                "source": safe_source(source),
                "labelLanguage": None,
                "depth": None,
                "requires": sorted(set(requires)),
            }
        )

    def _end(self, source: str) -> _Node | None:
        """The node a relation end names; the company root of an Ontaix export stands for the
        import's parent."""
        if source in self.roots:
            return _Node(OntologyItem(source=source, root=True), "", None)
        return self.nodes.get(self.alias.get(source, source))

    def _attributes(self) -> None:
        """One taught attribute draft per value, after its concept's draft."""
        for node in self.nodes.values():
            seen: set[str] = set()
            for attribute in node.item.attributes:
                name = unicodedata.normalize("NFKC", attribute.name).strip()
                value = attribute.value.strip()
                valid = (
                    0 < len(name) <= MAX_ATTRIBUTE_NAME_CHARS
                    and 0 < len(value) <= MAX_ATTRIBUTE_VALUE_CHARS
                    and attribute.type in TAUGHT_TYPES
                    and not has_refused_character(name)
                )
                if not valid:
                    self._skip(node.item.source, "unsupported_axiom", node.label)
                    continue
                if name.lower() in seen:
                    continue
                seen.add(name.lower())
                draft: dict[str, Any] = {"type": "attr"}
                requires: list[int] = []
                if node.existing is not None:
                    draft["conceptId"] = str(node.existing.id)
                else:
                    draft["conceptLabel"] = node.label
                    draft["companyId"] = str(self.target.company_id)
                    if node.draft_index is not None:
                        requires.append(node.draft_index)
                draft.update({"name": name, "attributeType": attribute.type, "value": value})
                self.tree.drafts.append(draft)
                self.tree.notes.append(
                    {
                        "source": safe_source(node.item.source),
                        "labelLanguage": None,
                        "depth": None,
                        "requires": requires,
                    }
                )

    def _skip(self, source: str, reason: SkipReason, label: str | None = None) -> None:
        if len(self.tree.skipped) >= MAX_SKIPPED:
            return
        entry: dict[str, Any] = {"source": safe_source(source), "reason": reason}
        if label is not None and reason != "invalid_label":
            entry["label"] = label
        self.tree.skipped.append(entry)
