"""Reads a gold source into the expected tree of a bake-off case, whatever its format.

The format comes from the file's suffix and, where a suffix is shared, from its content:

- `.csv`, `.tsv` -> CSV table; `.xlsx`, `.xlsm` -> Excel table; `.obo` -> OBO; `.owx` -> OWL/XML.
- Text starting with an XML tag: root `Ontology` in the OWL namespace without RDF attributes is
  OWL/XML, anything else (`rdf:RDF`, a node element) is RDF/XML. This holds for `.owl`, `.rdf`,
  `.xml` alike.
- Text starting with `{` or `[`: JSON-LD when it has `@context`, `@graph` or `@id` (always for
  `.jsonld`), otherwise a plain JSON tree or graph.
- `format-version:` or a `[Term]` stanza -> OBO; otherwise `.nt` is N-Triples, `.n3` is N3 and
  everything else Turtle.
- An RDF graph where SKOS concepts outnumber OWL/RDFS classes is read as a SKOS taxonomy.

Run `python -m evals.gold.loader <path> --company NAME` to print what a source yields.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from defusedxml import ElementTree

from evals.gold.gold_tree import GoldTree
from evals.gold.json_gold import is_json_ld, load_json
from evals.gold.obo_gold import load_obo
from evals.gold.owl_xml_gold import OWL_NS, load_owl_xml
from evals.gold.rdf_gold import import_graph, parse_graph
from evals.gold.skos_gold import import_skos, is_skos
from evals.gold.table_gold import TABLE_SUFFIXES, load_table

GOLD_SUFFIXES: tuple[str, ...] = (
    ".ttl",
    ".rdf",
    ".owl",
    ".xml",
    ".owx",
    ".nt",
    ".n3",
    ".jsonld",
    ".json",
    ".obo",
    *TABLE_SUFFIXES,
)

# Detected format -> rdflib parser name.
_RDF_PARSERS = {
    "turtle": "turtle",
    "n-triples": "nt",
    "n3": "n3",
    "rdf-xml": "xml",
    "json-ld": "json-ld",
}
_RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_XML_START = re.compile(r"^<(\?xml|!|[A-Za-z_][\w.\-]*(:[A-Za-z_][\w.\-]*)?[\s/>])")
_SNIFF_BYTES = 8192


def load_gold(path: Path, company: str) -> GoldTree:
    """The expected tree, optional labels and import report of a gold source."""
    fmt = detect_format(path)
    if fmt in _RDF_PARSERS:
        graph = parse_graph(path, _RDF_PARSERS[fmt])
        tree = (
            import_skos(graph, company, f"skos/{fmt}")
            if is_skos(graph)
            else import_graph(graph, company, fmt)
        )
    elif fmt == "owl-xml":
        tree = load_owl_xml(path, company)
    elif fmt == "obo":
        tree = load_obo(path, company)
    elif fmt in ("csv", "xlsx"):
        tree = load_table(path, company)
    else:
        tree = load_json(path, company)
    tree.report = {"source": path.name, **tree.report}
    return tree


def detect_format(path: Path) -> str:
    """One of turtle, n-triples, n3, rdf-xml, json-ld, owl-xml, obo, csv, xlsx, json."""
    suffix = path.suffix.lower()
    if suffix not in GOLD_SUFFIXES:
        raise ValueError(
            f"{path.name}: unsupported gold file (accepted: {', '.join(GOLD_SUFFIXES)})"
        )
    if suffix in (".csv", ".tsv"):
        return "csv"
    if suffix in TABLE_SUFFIXES:
        return "xlsx"
    if suffix == ".obo":
        return "obo"
    with path.open("rb") as handle:
        head = handle.read(_SNIFF_BYTES).decode("utf-8", errors="replace").lstrip("﻿ \t\r\n")
    if _XML_START.match(head):
        return _xml_format(path)
    if head.startswith(("{", "[")):
        if suffix == ".jsonld":
            return "json-ld"
        return "json-ld" if is_json_ld(json.loads(path.read_text("utf-8-sig"))) else "json"
    if head.startswith(("Prefix(", "Ontology(")):
        raise ValueError(f"{path.name}: OWL functional syntax is not supported")
    if head.startswith("format-version:") or re.search(r"^\[Term\]", head, re.MULTILINE):
        return "obo"
    return {".nt": "n-triples", ".n3": "n3"}.get(suffix, "turtle")


def _xml_format(path: Path) -> str:
    for _, root in ElementTree.iterparse(path, events=("start",)):
        rdf_attributes = any(a.startswith(f"{{{_RDF_NS}}}") for a in root.attrib)
        if root.tag == f"{{{OWL_NS}}}Ontology" and not rdf_attributes:
            return "owl-xml"
        return "rdf-xml"
    raise ValueError(f"{path.name}: empty XML document")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print what a gold source yields.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--company", required=True, help="the company name, root of the tree")
    args = parser.parse_args(argv)
    tree = load_gold(args.path, args.company)
    print(f"format:    {tree.report['format']}")
    print(f"concepts:  {len(tree.expected.concepts)}")
    print(f"relations: {len(tree.expected.relations)}")
    print(f"optional:  {len(tree.optional)}")
    print(f"max depth: {tree.report['maxDepth']}")
    print(json.dumps(tree.report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
