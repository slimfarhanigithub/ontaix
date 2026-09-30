"""Whether an uploaded file is a document or an ontology, decided from its bytes first.

The bytes decide whenever they are unambiguous: PDF, Word, PowerPoint and HTML are documents;
RDF/XML, OWL/XML, JSON-LD, OBO, Turtle with a directive and N-Triples are ontologies; a CSV or
XLSX table is an ontology when its header row is a hierarchy header (`label` and `parent`, or
`Level <n>` columns) and a document otherwise. Text that shows no ontology format on its own
follows its extension, else its declared media type: an ontology extension or type names the
format, anything else is a document. Every result also names the document media type the bytes
read as, so the file can still be read as a document.

Only an Office archive is read whole, and only in a child process; any other file is judged by
its first 64 KiB, cut back to its last complete line, so detection costs the same for any size.
Whether the rest of the file is valid text is checked by the import that reads it.
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
    UTF16_BOMS,
    XLSX,
    ZIP_SIGNATURE,
    decode_text,
    sniff,
)
from app.utilities.hierarchy_table_reader import is_csv_hierarchy, is_xlsx_hierarchy
from app.utilities.ontology_formats import content_format, declared_format

ImportKind = Literal["document", "ontology"]

# How much of a file other than an Office archive detection reads.
PREFIX_BYTES = 64 * 1024
# The most bytes a cut can leave of one incomplete UTF-8 or UTF-16 character.
_MAX_PARTIAL_CHARACTER = 3

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
    unknown or macro-enabled archives and binary data. An Office archive is read whole; any
    other file by its first `PREFIX_BYTES`."""
    if not data.startswith(ZIP_SIGNATURE):
        data = text_prefix(data)
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


def text_prefix(data: bytes) -> bytes:
    """The first `PREFIX_BYTES` of `data`, cut back to the end of its last complete line and to
    a whole character; `data` itself when it is no longer."""
    if len(data) <= PREFIX_BYTES:
        return data
    head = data[:PREFIX_BYTES]
    if head.startswith(b"\xfe\xff"):
        newline = b"\x00\n"
    elif head.startswith(UTF16_BOMS):
        newline = b"\n\x00"
    else:
        newline = b"\n"
    # A UTF-16 line break is one whole code unit, at an even offset after the byte order mark.
    end = head.rfind(newline)
    while end > 0 and len(newline) == 2 and end % 2:
        end = head.rfind(newline, 0, end + 1)
    if end > 0:
        return head[: end + len(newline)]
    for cut in range(_MAX_PARTIAL_CHARACTER + 1):
        try:
            decode_text(head[: len(head) - cut])
        except UnicodeDecodeError:
            continue
        return head[: len(head) - cut]
    return head


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
