"""Export writers without a database: every format parses back, the four OWL formats are one
graph and map back to the same drafts, text is escaped, and the Word document has no ids."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime

import pytest
from docx import Document
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from app.models.export.export_snapshot import (
    ExportAttribute,
    ExportCompany,
    ExportConcept,
    ExportDomain,
    ExportRelation,
    ExportSnapshot,
)
from app.utilities.export_iris import slug
from app.utilities.export_writer import write_export
from app.utilities.ontaix_vocabulary import OX
from app.utilities.ontology_mapping import MappingTarget, map_ontology
from app.utilities.ontology_reader import read_ontology

RDFLIB_FORMATS = {"owl": "xml", "turtle": "turtle", "jsonld": "json-ld", "skos": "turtle"}
IMPORT_FORMATS = {"owl": "rdf_xml", "owx": "owl_xml", "turtle": "turtle", "jsonld": "json_ld"}
TRICKY = 'Pumps & "valves" · Pompes'


def snapshot() -> ExportSnapshot:
    home, other = uuid.uuid4(), uuid.uuid4()
    root, plant, machine, crew, big, valve = (uuid.uuid4() for _ in range(6))
    return ExportSnapshot(
        scope="company",
        scope_name="Northwind",
        tenant_name="Tenant",
        exported_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
        base_iri="urn:ontaix:",
        language="en",
        companies=[ExportCompany(home, "northwind", "Northwind", "pumps", ("production",))],
        domains=[ExportDomain("production", "Production", "Ana", "#3fb8a9")],
        concepts=[
            ExportConcept(root, home, "Northwind", "root"),
            ExportConcept(plant, home, "Plant", "birth", "production", root, "operates"),
            ExportConcept(
                machine,
                home,
                TRICKY,
                "birth",
                "production",
                plant,
                "has",
                attributes=(
                    ExportAttribute("Rated power", "number", "75.5"),
                    ExportAttribute("Commissioned", "date", "2021-04-01"),
                    ExportAttribute("Note", "text", 'a & b "quoted"'),
                    ExportAttribute("Serial", "id", None, "dbo.machine.serial", 90),
                ),
            ),
            ExportConcept(crew, home, "Crew", "birth", "production", machine, "services", True),
            ExportConcept(big, home, "Big machine", "spec", "production", machine, rule="> 5 t"),
        ],
        relations=[
            ExportRelation(crew, plant, "rel", "works in"),
            ExportRelation(big, plant, "isa", "is a"),
            ExportRelation(machine, valve, "same", "equivalent to"),
        ],
        outside=[ExportConcept(valve, other, "Valve", "birth", "production", None, "makes")],
        outside_companies=[ExportCompany(other, "aurora", "Aurora", "")],
    )


@pytest.mark.parametrize("fmt", sorted(RDFLIB_FORMATS))
def test_each_rdf_format_parses_back(fmt: str) -> None:
    graph = Graph().parse(data=write_export(snapshot(), fmt), format=RDFLIB_FORMATS[fmt])

    label = SKOS.prefLabel if fmt == "skos" else RDFS.label
    labels = {str(o) for o in graph.objects(None, label)}
    assert TRICKY in labels and "Plant" in labels


def test_the_four_owl_formats_are_one_graph() -> None:
    snap = snapshot()
    graphs = {
        fmt: Graph().parse(data=write_export(snap, fmt), format=rdflib)
        for fmt, rdflib in RDFLIB_FORMATS.items()
        if fmt != "skos"
    }
    ground = {fmt: _ground(g) for fmt, g in graphs.items()}
    assert ground["turtle"] == ground["owl"] == ground["jsonld"]
    assert len(graphs["turtle"]) == len(graphs["owl"]) == len(graphs["jsonld"])
    owl = graphs["owl"]
    classes = {str(owl.value(c, RDFS.label)): c for c in owl.subjects(RDF.type, OWL.Class)}
    machine, plant = classes[TRICKY], classes["Plant"]
    assert (machine, OX.bornFrom, plant) in owl and (machine, RDFS.subClassOf, plant) not in owl
    assert (classes["Big machine"], RDFS.subClassOf, machine) in owl
    assert owl.value(machine, OX.domain) == Literal("production")
    powers = [o for p, o in owl.predicate_objects(machine) if str(p).endswith("/a/rated-power")]
    assert powers == [Literal("75.5", datatype=XSD.decimal)]
    source = next(owl.subjects(RDF.type, OWL.DatatypeProperty))
    assert owl.value(source, RDFS.range) == XSD.string
    assert str(owl.value(source, OX.column)) == "dbo.machine.serial"
    assert (URIRef("urn:ontaix:northwind"), RDF.type, OX.Company) in owl


def test_the_four_owl_formats_map_back_to_the_same_drafts() -> None:
    snap = snapshot()
    target = MappingTarget(
        company_id=uuid.uuid4(),
        parent_id=uuid.uuid4(),
        parent_domain_key=None,
        domain_keys=frozenset({"production", "sales"}),
        domain_key=None,
        languages=("en",),
        individuals="skip",
        max_nodes=100,
    )
    trees = {
        fmt: map_ontology(read_ontology(write_export(snap, fmt), parsed), target, [], set())
        for fmt, parsed in IMPORT_FORMATS.items()
    }
    drafts = trees["owl"].drafts
    for tree in trees.values():
        assert tree.drafts == drafts
    by_label = {
        d.get("label") or f"{d.get('aLabel')} {d['action']} {d.get('bLabel')}": d
        for d in drafts
        if d["type"] != "attr"
    }
    assert by_label["Plant"]["parentId"] == str(target.parent_id)
    assert by_label["Plant"]["action"] == "operates"
    assert by_label["Crew"]["reverse"] is True and by_label["Crew"]["action"] == "services"
    assert by_label["Big machine"] == {
        "type": "spec",
        "companyId": str(target.company_id),
        "label": "Big machine",
        "domainKey": "production",
        "parentLabel": by_label["Big machine"]["parentLabel"],
        "rule": "> 5 t",
    }
    assert "Crew works in Plant" in by_label and "Big machine is a Plant" in by_label
    assert not any(k.endswith(" has " + by_label["Crew"]["parentLabel"]) for k in by_label)
    attributes = {
        (d["name"], d["attributeType"], d["value"]) for d in drafts if d["type"] == "attr"
    }
    assert attributes == {
        ("Rated power", "number", "75.5"),
        ("Commissioned", "date", "2021-04-01"),
        ("Note", "text", 'a & b "quoted"'),
    }
    reasons = {s["reason"] for s in trees["owl"].skipped}
    assert reasons == {"datatype_property", "equivalence_not_imported"}


def test_an_unknown_domain_takes_the_parents_and_is_reported() -> None:
    snap = snapshot()
    target = MappingTarget(
        company_id=uuid.uuid4(),
        parent_id=uuid.uuid4(),
        parent_domain_key=None,
        domain_keys=frozenset({"sales"}),
        domain_key=None,
        languages=("en",),
        individuals="skip",
        max_nodes=100,
    )
    tree = map_ontology(read_ontology(write_export(snap, "turtle"), "turtle"), target, [], set())

    assert {s["reason"] for s in tree.skipped} >= {"unknown_domain"}
    assert {d["domainKey"] for d in tree.drafts if "domainKey" in d} == {"production"}


def test_the_word_document_has_the_sections_and_no_ids() -> None:
    document = Document(io.BytesIO(write_export(snapshot(), "docx")))

    headings = [(p.style.name, p.text) for p in document.paragraphs if p.style.name != "Normal"]
    assert ("Title", "Ontaix export") in headings
    assert ("Heading 1", "Northwind") in headings
    for name in ("Domains", "Entity hierarchy", "Relationships", "Equivalences"):
        assert ("Heading 2", name) in headings
    entries = [p.text for p in document.paragraphs if p.style.name == "List Bullet"]
    assert any(e.startswith(TRICKY) and "Rated power: 75.5" in e for e in entries)
    assert any(e.startswith("Big machine") and f"is a {TRICKY}" in e for e in entries)
    assert any(e.startswith(TRICKY) and "is equivalent to Valve (Aurora)" in e for e in entries)
    rows = [[c.text for c in r.cells] for t in document.tables for r in t.rows]
    assert ["Crew", "services", TRICKY] in rows and ["Crew", "works in", "Plant"] in rows
    text = " ".join([p.text for p in document.paragraphs] + [c for r in rows for c in r])
    assert "urn:" not in text and not any(str(c.id) in text for c in snapshot().concepts)


def test_slugs_are_ascii_and_never_empty() -> None:
    assert slug("works in") == "works-in"
    assert slug("Gère") == "g-re"
    assert slug("···") == "x"


def _ground(graph: Graph) -> set[tuple[str, str, str]]:
    return {
        (str(s), str(p), str(o))
        for s, p, o in graph
        if not isinstance(s, BNode) and not isinstance(o, BNode)
    }
