"""The expected tree of a bake-off case read from a gold source (an ontology, a taxonomy, a
process framework, ...): the concepts and relations it expects, the labels that are optional,
and a report of what the importer read and what it ignored."""

from __future__ import annotations

from dataclasses import dataclass, field

from evals.teach_case import Expected


@dataclass
class GoldTree:
    expected: Expected
    # Labels that are neither invented nor missed when drafted (individuals, instances, ...).
    optional: list[str]
    # What was read (format, counts, max depth) and what was ignored (axioms by predicate,
    # datatype properties, datatype restrictions, skipped rows, obsolete terms, ...).
    report: dict[str, object] = field(default_factory=dict)
