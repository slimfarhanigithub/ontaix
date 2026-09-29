"""One entry for reading any supported ontology format and mapping it, run in a child process."""

from __future__ import annotations

import uuid

from app.models.ontology_import.parsed_ontology import OntologyFormat, ParsedOntology
from app.utilities.hierarchy_table_reader import read_csv_hierarchy, read_xlsx_hierarchy
from app.utilities.obo_reader import read_obo
from app.utilities.ontology_mapping import ExistingConcept, MappedTree, MappingTarget, map_ontology
from app.utilities.owl_xml_reader import read_owl_xml
from app.utilities.rdf_ontology_reader import read_rdf


def read_ontology(data: bytes, fmt: OntologyFormat) -> ParsedOntology:
    """The parsed content of a file of a detected format."""
    if fmt == "owl_xml":
        return read_owl_xml(data)
    if fmt == "obo":
        return read_obo(data)
    if fmt == "csv":
        return read_csv_hierarchy(data)
    if fmt == "xlsx":
        return read_xlsx_hierarchy(data)
    return read_rdf(data, fmt)


def read_and_map(
    data: bytes,
    fmt: OntologyFormat,
    target: MappingTarget,
    existing: list[ExistingConcept],
    existing_relations: set[tuple[uuid.UUID, uuid.UUID, str]],
) -> MappedTree:
    """Parse and map in one step, so a child process returns only the tree."""
    return map_ontology(read_ontology(data, fmt), target, existing, existing_relations)
