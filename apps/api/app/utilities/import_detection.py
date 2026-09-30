"""Whether an uploaded file is a document or an ontology, decided from its bytes first.

The bytes decide whenever they are unambiguous: PDF, Word, PowerPoint and HTML are documents;
RDF/XML, OWL/XML, JSON-LD, OBO, Turtle with a directive and N-Triples are ontologies; a CSV or
XLSX table is an ontology when its header row is a hierarchy header (`label` and `parent`, or
`Level <n>` columns) and a document otherwise. Text that shows no ontology format on its own
follows its extension, else its declared media type: an ontology extension or type names the
format, anything else is a document. Every result also names the document media type the bytes
read as, so the file can still be read as a document.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models.ontology_import.parsed_ontology import OntologyFormat
from app.utilities.document_text import (
    MEDIA_TYPE_BY_EXTENSION,
    SNIFFED_TEXT,
    TEXT_CSV,
    TEXT_PLAIN,
    TEXT_TYPES,
    XLSX,
    sniff,
)
from app.utilities.hierarchy_table_reader import is_csv_hierarchy, is_xlsx_hierarchy
from app.utilities.ontology_formats import content_format, declared_format

ImportKind = Literal["document", "ontology"]

# Formats a CSV or XLSX extension declares are decided by the header row, never by extension.
_TABLE_FORMATS: tuple[OntologyFormat, ...] = ("csv", "xlsx")


@dataclass(frozen=True)
class DetectedImport:
    kind: ImportKind
    # The ontology format when `kind` is ontology, else None.
    format: OntologyFormat | None
    # The document media type the bytes read as.
    media_type: str


def detect_import(file_name: str, content_type: str | None, data: bytes) -> DetectedImport:
    """The detected kind, ontology format and document media type. Raises
    `UnsupportedDocumentError` for bytes no import reads: legacy or encrypted Office files,
    unknown or macro-enabled archives and binary data."""
    sniffed = sniff(data)
    if sniffed == XLSX:
        if is_xlsx_hierarchy(data):
            return DetectedImport("ontology", "xlsx", XLSX)
        return DetectedImport("document", None, XLSX)
    if sniffed != SNIFFED_TEXT:
        return DetectedImport("document", None, sniffed)
    media_type = _text_media_type(file_name, content_type)
    fmt = content_format(data)
    if fmt is None and media_type == TEXT_CSV and is_csv_hierarchy(data):
        fmt = "csv"
    if fmt is None:
        declared = declared_format(file_name, content_type)
        if declared not in _TABLE_FORMATS and _declared_media_type(file_name) is None:
            fmt = declared
    if fmt is None:
        return DetectedImport("document", None, media_type)
    return DetectedImport("ontology", fmt, media_type)


def _text_media_type(file_name: str, content_type: str | None) -> str:
    """The text document type the extension, else the declared media type, names; plain text
    when neither names one."""
    by_extension = _declared_media_type(file_name)
    if by_extension in TEXT_TYPES:
        return by_extension
    declared = (content_type or "").split(";")[0].strip().lower()
    if by_extension is None and declared in TEXT_TYPES:
        return declared
    return TEXT_PLAIN


def _declared_media_type(file_name: str) -> str | None:
    dot = file_name.rfind(".")
    return MEDIA_TYPE_BY_EXTENSION.get(file_name[dot:].lower()) if dot >= 0 else None
