# ADR 0016: Export

Status: Accepted. Export, with OWL as a first-class format, is an owner decision, final (decision rows 141 and 142); the mapping details are approved under owner delegation (2026-09-30).

## Context

A business modelled in Ontaix must be able to leave it: as an ontology other tools read, OWL first, and as a document people read. Ontology import (ADR 0012) already reads OWL, SKOS and OBO; export is its counterpart, and an OWL export must import back into the same model.

## Decision

### Endpoint

`GET /export?scope=company|domain|all&companyId=&domainProductId=&format=owl|owx|turtle|jsonld|skos|docx`, permission `model.read`. Generated server-side, synchronously, in a child process within 60 seconds, from the approved model only (pending concepts, relations and attributes are left out). Only what the caller may read: `scope=all` covers every company the caller may read, and a cross-company relation or equivalence is included only when both companies are readable. At most `ONTAIX_EXPORT_MAX_CONCEPTS` concepts (default 20,000, `413` above). One unit of the hourly `export` budget per call (default 20 per caller, `ONTAIX_EXPORT_PER_HOUR`). Audited as kind `export` with the scope and format, never the content. `Content-Disposition: attachment` with a file name from the scope and the date; `Cache-Control: no-store`.

```mermaid
flowchart LR
  req[GET /export] --> checks[model.read, scope readable, export budget, size]
  checks --> read[Read approved model of the scope - readable companies only]
  read --> graph[Build one RDF graph - Ontaix mapping]
  graph --> owl[owl - OWL 2 RDF/XML .owl, primary]
  graph --> owx[owx - OWL 2 OWL/XML .owx]
  graph --> ttl[turtle - OWL 2 Turtle .ttl]
  graph --> jsonld[jsonld - OWL 2 JSON-LD]
  read --> skos[skos - SKOS Turtle]
  read --> docx[docx - Word document]
  owl -.round trip test.-> imp[POST /ontology-imports into an empty company - same model]
```

### Formats

| `format` | Media type | File | Content |
|---|---|---|---|
| `owl` | `application/rdf+xml` | `.owl` | OWL 2 in RDF/XML, the primary export |
| `owx` | `application/owl+xml` | `.owx` | OWL 2 in OWL/XML |
| `turtle` | `text/turtle` | `.ttl` | OWL 2 in Turtle |
| `jsonld` | `application/ld+json` | `.jsonld` | OWL 2 in JSON-LD, with an inline `@context` |
| `skos` | `text/turtle` | `.skos.ttl` | The SKOS mapping below |
| `docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `.docx` | A readable description |

The four OWL formats carry exactly the same axioms and annotations; they are serialisations of one graph.

### IRIs And Vocabulary

- Base: `ONTAIX_EXPORT_BASE_IRI` (default `urn:ontaix:`). A company is `<base><companyKey>`, a concept `<base><companyKey>/c/<conceptId>`, a relation's property `<base><companyKey>/p/<slug of the action>`, a taught attribute's property `<base><companyKey>/a/<slug of the name>`. Ids are the concepts' uuids, so IRIs are stable across exports; no tenant name or user appears in an IRI.
- The Ontaix annotation vocabulary is `https://ontaix.dev/ns#` (prefix `ox:`), declared as annotation properties in every file: `ox:company`, `ox:domain`, `ox:bornFrom`, `ox:birthAction`, `ox:birthReverse`, `ox:action`, `ox:attributeValue`, `ox:attributeType`, `ox:column`, `ox:fill`, `ox:rule`.

### OWL Mapping

| Ontaix | OWL 2 |
|---|---|
| Export | One `owl:Ontology` (`<base>export/<scope>/<date>`) with `rdfs:label`, `owl:versionInfo` (the export time) and `rdfs:comment` |
| Company | `ox:company` annotation on every class and property (the company's name as `rdfs:label` of the company IRI, declared as an `owl:NamedIndividual` of `ox:Company`) |
| Domain | `ox:domain` annotation (the domain key) on every class; the tenant domains in the scope as `owl:NamedIndividual`s of `ox:Domain` with `rdfs:label`, `ox:key`, `ox:color` and `ox:owner` |
| Concept (not the root) | `owl:Class` with `rdfs:label` (the label, `@en` unless the tenant language says otherwise), `ox:domain`, `ox:company`; a specialisation's rule as `ox:rule` |
| Company root | `owl:Class` with the company's name, annotated `ox:company` - the top of the company's tree |
| Specialisation (`is a`) | `rdfs:subClassOf` the parent class - a true subclass |
| Birth relation (child born from parent with an action) | `ox:bornFrom` the parent class, `ox:birthAction` the action, `ox:birthReverse` when reversed; plus the relation axioms of the row below for the action. Not `rdfs:subClassOf`: `Services has Offerings` does not make every Offering a Service, and a reasoner would infer false facts |
| Relation (`rel`, including birth actions) | An `owl:ObjectProperty` per distinct action per company, `rdfs:label` the action, `rdfs:domain` and `rdfs:range` the union of the subject and object classes it links (a single class when one), and for each relation the assertion `Subject rdfs:subClassOf [ owl:onProperty P ; owl:someValuesFrom Object ]` - the axiom ontology import reads back as a relation |
| Equivalence (`same`) | `owl:equivalentClass` (only when both companies are readable) |
| Conflict (`clash`) | Not exported as an axiom; `ox:conflictsWith` annotation |
| Attribute read from a source | `owl:DatatypeProperty` with `rdfs:label` the name, `rdfs:domain` the class, `rdfs:range` the XSD type of `type` (`id` and `text` `xsd:string`, `number` `xsd:decimal`, `date` `xsd:date`, `ref` `xsd:anyURI`), annotated `ox:column` and `ox:fill` |
| Taught attribute (a value stated for the concept) | An `owl:AnnotationProperty` per name with `rdfs:label` the name, and the annotation assertion on the class with the value as a typed literal (`xsd:string`, `xsd:decimal`, `xsd:date`), plus `ox:attributeType`. An annotation because the value describes the class, not its individuals, and a datatype property would need individuals |
| Bindings and sources | Not exported (they describe connections, not the model) |

Only asserted structure is written; no inference is materialised.

### SKOS Mapping

One `skos:ConceptScheme` per company (`skos:prefLabel` the company name); each concept a `skos:Concept` with `skos:prefLabel`, `skos:inScheme`, `skos:broader` its birth parent or its specialisation parent (`skos:topConceptOf` for the root's children); relations as `skos:related` plus the `ox:action` annotation on a reified statement; equivalences as `skos:exactMatch`; each domain a `skos:Collection` with `skos:member`; taught attributes as `skos:note` "`<name>: <value>`". SKOS carries the tree for thesaurus tools; it does not round-trip actions exactly.

### Round Trip

An OWL export (any of the four formats) of one company imports back through `POST /ontology-imports` into an empty company of a tenant with the same domains and produces the same approved model after approval: the same labels, the same birth parents and actions (from `ox:bornFrom` and `ox:birthAction`), the same specialisations (`rdfs:subClassOf` to a named class), the same relations (`someValuesFrom` restrictions), the same domains (`ox:domain`) and the same taught attributes (annotation assertions of properties typed by `ox:attributeType`). Ontology import reads the `ox:` annotations when present (ADR 0012, amended by decision row 142). Out of the round trip, by design: source attributes, bindings and sources (they need a connected source), cross-company relations and equivalences (import is per company), and conflicts. A contract test exports the fixture companies in each OWL format, re-imports each into an empty company, approves everything, and compares the models; it fails on any difference.

### Word Document

Generated with a library in `apps/api` (no Office installation, no macros, no fields, no external links): a title page with the scope, the date and the exporting tenant's name; per company a section with its domains (name, owner, colour swatch as a table cell shade), then the entity hierarchy as nested lists following the birth tree (each entry the label, its domain, `is a` parents, and its attributes as `name: value`), then a table of relationships (subject, action, object), then equivalences to other readable companies. All text is inserted as plain runs, so no label can become markup or a field. The same size limit applies.

### Security

Export reads only the approved model the caller may read and writes nothing. Labels and values are escaped by the RDF and XML serialisers and inserted as text runs in the document. The budget and the size limit bound its cost; the audit entry records who exported what scope, when, in which format.

## Consequences

- OWL 2 is a first-class exit, in RDF/XML primarily, with OWL/XML, Turtle and JSON-LD, and a Word document for people.
- Birth relations are exported as `ox:` annotations plus existential restrictions, not as subclassing, which keeps the OWL semantics true; tools that want a pure tree use the SKOS export or `ox:bornFrom`.
- Ontology import learns the `ox:` vocabulary so an OWL export round-trips, checked by a test.
- One endpoint, one budget value, one audit kind; no table, no event.
