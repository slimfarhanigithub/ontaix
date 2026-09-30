"""Which ontology format an upload is: detected from the bytes, checked against the declared type.

RDF/XML and OWL/XML are told apart by their root element, read with no DTD; JSON-LD is JSON
naming an `@context` or `@graph` key; OBO has a `format-version:` header and `[Term]` stanzas;
N-Triples is one full triple per line and anything else textual is Turtle; an XLSX hierarchy
is sniffed like an Excel document import; CSV is taken as declared. The detected format must
agree with the format the caller chose, else with the file extension, else with the declared
media type. `content_format` names the format that text shows on its own, with no declaration,
for telling an ontology from a document.
"""

from __future__ import annotations

import io
import re

import defusedxml.ElementTree as DefusedET
from defusedxml import DefusedXmlException

from app.models.ontology_import.parsed_ontology import OntologyFormat
from app.utilities.document_errors import UnsupportedDocumentError
from app.utilities.document_text import OLE_SIGNATURE, ZIP_SIGNATURE, decode_text
from app.utilities.ooxml_archive import ooxml_kind

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
OWL_NS = "http://www.w3.org/2002/07/owl#"

# The formats each extension or media type may hold.
FORMATS_BY_EXTENSION: dict[str, tuple[OntologyFormat, ...]] = {
    ".rdf": ("rdf_xml",),
    ".xml": ("rdf_xml", "owl_xml"),
    ".owl": ("rdf_xml", "owl_xml"),
    ".owx": ("owl_xml",),
    ".ttl": ("turtle", "n_triples"),
    ".jsonld": ("json_ld",),
    ".json": ("json_ld",),
    ".nt": ("n_triples",),
    ".obo": ("obo",),
    ".csv": ("csv",),
    ".xlsx": ("xlsx",),
}
FORMATS_BY_MEDIA_TYPE: dict[str, tuple[OntologyFormat, ...]] = {
    "application/rdf+xml": ("rdf_xml",),
    "application/owl+xml": ("owl_xml",),
    "text/turtle": ("turtle", "n_triples"),
    "application/ld+json": ("json_ld",),
    "application/n-triples": ("n_triples",),
    "text/csv": ("csv",),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ("xlsx",),
}

_JSON_LD_KEY = re.compile(r'"@(?:context|graph)"\s*:')
# A Turtle `@prefix` or `@base` directive, or its SPARQL-style `PREFIX` or `BASE` form.
_TURTLE_DIRECTIVE = re.compile(r"^\s*(?:@prefix|@base|PREFIX|BASE)\s+\S*\s*<", re.MULTILINE)
_NTRIPLE = re.compile(
    r'^(<[^>\s]*>|_:\S+)\s+<[^>\s]*>\s+(<[^>\s]*>|_:\S+|"(?:[^"\\]|\\.)*"(\^\^<[^>\s]*>|@[A-Za-z0-9-]+)?)\s*\.\s*(#.*)?$'
)


def detect_format(
    file_name: str, content_type: str | None, data: bytes, chosen: OntologyFormat | None = None
) -> OntologyFormat:
    """The detected format, or `UnsupportedDocumentError` when it is none of the supported
    ones or disagrees with the declared one: `chosen` when given (Turtle also holds
    N-Triples), else the file's extension, else its media type."""
    allowed = _chosen(chosen) if chosen else _declared(file_name, content_type)
    if allowed is None:
        raise UnsupportedDocumentError(
            "OWL (RDF/XML, Turtle, OWL/XML, JSON-LD, N-Triples), SKOS, OBO, CSV and Excel "
            "hierarchies are supported"
        )
    sniffed = _sniff(data, allowed)
    if sniffed not in allowed:
        raise UnsupportedDocumentError(
            f"the file reads as {sniffed.replace('_', ' ')} but "
            + ("the chosen format" if chosen else "its name or type")
            + " says otherwise"
        )
    # A Turtle file whose statements are all full triples is still read as Turtle.
    if sniffed == "n_triples" and "n_triples" != allowed[0]:
        return allowed[0]
    return sniffed


def content_format(data: bytes) -> OntologyFormat | None:
    """The ontology format that the text of `data` shows with no declaration: an RDF/XML or
    OWL/XML root, JSON naming `@context` or `@graph`, an OBO header with terms, a Turtle
    directive, or lines that are all full N-Triples; None for any other bytes. A CSV or XLSX
    hierarchy is told by its header row, in `hierarchy_table_reader`."""
    try:
        text = decode_text(data)
    except UnicodeDecodeError:
        return None
    head = text.lstrip()
    if head.startswith("<"):
        try:
            return _xml_format(data)
        except UnsupportedDocumentError:
            pass
    if head.startswith(("{", "[")):
        return "json_ld" if _JSON_LD_KEY.search(text) else None
    try:
        return _obo(text)
    except UnsupportedDocumentError:
        pass
    if _TURTLE_DIRECTIVE.search(text[:65536]):
        return "turtle"
    if _triples_or_turtle(text) == "n_triples":
        return "n_triples"
    return None


def declared_format(file_name: str, content_type: str | None) -> OntologyFormat | None:
    """The first ontology format the extension, else the media type, declares; None when
    neither names one."""
    allowed = _declared(file_name, content_type)
    return allowed[0] if allowed else None


def _chosen(chosen: OntologyFormat) -> tuple[OntologyFormat, ...]:
    return ("turtle", "n_triples") if chosen == "turtle" else (chosen,)


def _declared(file_name: str, content_type: str | None) -> tuple[OntologyFormat, ...] | None:
    dot = file_name.rfind(".")
    if dot >= 0 and file_name[dot:].lower() in FORMATS_BY_EXTENSION:
        return FORMATS_BY_EXTENSION[file_name[dot:].lower()]
    declared = (content_type or "").split(";")[0].strip().lower()
    return FORMATS_BY_MEDIA_TYPE.get(declared)


def _sniff(data: bytes, allowed: tuple[OntologyFormat, ...]) -> OntologyFormat:
    if data.startswith(OLE_SIGNATURE):
        raise UnsupportedDocumentError("legacy binary and encrypted Office files are not read")
    if data.startswith(ZIP_SIGNATURE):
        if ooxml_kind(data) != "xlsx":
            raise UnsupportedDocumentError("only an Excel workbook is read as a hierarchy")
        return "xlsx"
    try:
        text = decode_text(data)
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError("the file is not UTF-8 text") from exc
    head = text.lstrip()
    # Turtle and N-Triples also open with `<` (a full IRI), so XML without a declaration or
    # doctype is tried only where declared.
    xml_declared = {"rdf_xml", "owl_xml"} & set(allowed)
    if head.startswith(("<?xml", "<!DOCTYPE", "<!doctype")) or (
        head.startswith("<") and xml_declared
    ):
        return _xml_format(data)
    if head.startswith(("{", "[")) and "json_ld" in allowed:
        return _json_ld(text)
    if "obo" in allowed:
        return _obo(text)
    if "csv" in allowed:
        return "csv"
    return _triples_or_turtle(text)


def _xml_format(data: bytes) -> OntologyFormat:
    """RDF/XML or OWL/XML by the root element, read with no DTD and no entities."""
    try:
        for _, element in DefusedET.iterparse(
            io.BytesIO(data),
            events=("start",),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        ):
            if element.tag == f"{{{RDF_NS}}}RDF":
                return "rdf_xml"
            if element.tag == f"{{{OWL_NS}}}Ontology":
                return "owl_xml"
            break
    except DefusedXmlException as exc:
        raise UnsupportedDocumentError("XML with a DTD or entities is not read") from exc
    except DefusedET.ParseError as exc:
        raise UnsupportedDocumentError("the XML is not well-formed") from exc
    raise UnsupportedDocumentError("the XML is neither RDF/XML nor OWL/XML")


def _json_ld(text: str) -> OntologyFormat:
    """JSON-LD when the text names an `@context` or `@graph` key. Nothing is parsed here: the
    JSON is parsed, depth-bounded, in the child process that reads it."""
    if _JSON_LD_KEY.search(text):
        return "json_ld"
    raise UnsupportedDocumentError("the JSON has no @context or @graph")


def _obo(text: str) -> OntologyFormat:
    lines = [line.strip() for line in text.splitlines()]
    if any(line.startswith("format-version:") for line in lines[:50]) and "[Term]" in lines:
        return "obo"
    raise UnsupportedDocumentError("the file has no OBO header and terms")


def _triples_or_turtle(text: str) -> OntologyFormat:
    statements = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if statements and all(_NTRIPLE.match(line) for line in statements[:1000]):
        return "n_triples"
    return "turtle"
