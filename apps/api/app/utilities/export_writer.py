"""One entry for writing an export snapshot in any format, run in a child process.

The four OWL formats are serialisations of one graph, so they carry the same axioms and
annotations; SKOS and the Word document are written from the same snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.export.export_snapshot import ExportFormat, ExportSnapshot
from app.utilities.export_docx import export_docx
from app.utilities.owl_export_graph import PREFIXES, owl_triples
from app.utilities.owl_xml_writer import owl_xml
from app.utilities.rdf_writers import json_ld, rdf_xml, turtle
from app.utilities.skos_export_graph import skos_triples


@dataclass(frozen=True)
class FormatInfo:
    media_type: str
    extension: str


FORMATS: dict[str, FormatInfo] = {
    "owl": FormatInfo("application/rdf+xml", ".owl"),
    "owx": FormatInfo("application/owl+xml", ".owx"),
    "turtle": FormatInfo("text/turtle", ".ttl"),
    "jsonld": FormatInfo("application/ld+json", ".jsonld"),
    "skos": FormatInfo("text/turtle", ".skos.ttl"),
    "docx": FormatInfo(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
    ),
}


def write_export(snapshot: ExportSnapshot, fmt: ExportFormat) -> bytes:
    if fmt == "docx":
        return export_docx(snapshot)
    if fmt == "skos":
        return turtle(skos_triples(snapshot), PREFIXES)
    triples = owl_triples(snapshot)
    if fmt == "owl":
        return rdf_xml(triples, PREFIXES)
    if fmt == "owx":
        return owl_xml(triples, PREFIXES)
    if fmt == "turtle":
        return turtle(triples, PREFIXES)
    # The JSON-LD context is inline: the graph's prefixes, so nothing is fetched to read it.
    return json_ld(triples, PREFIXES)
