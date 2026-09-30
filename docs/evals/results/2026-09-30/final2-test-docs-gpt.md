# Teach Bake-Off Report

Started 2026-09-29T23:42:09+00:00. Spent 17.2963 EUR of a 24.00 EUR budget (estimate before the run: 20.74 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@none | eu_data_zone | 0.639 | 0.535 | 0.572 | 1.000 | 25% | 87% | 79% | 84% | 69% | 1167 | 61 | 27% | 21 | 0 | 2133 | 17.2963 | 1.4 | 3.6 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | benchmarks:sentences | documents:sentences |
|---|---|---|
| gpt-6-sol@none | 7% / 18% / 6.933 | 50% / 72% / 10.363 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (49) | L2 (79) | L3 (126) | L4 (130) | L5 (64) | L6 (9) | L7 (0) | L8 (0) | L9 (0) | L10 (0) |
|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6-sol@none | 18% | 19% | 32% | 45% | 40% | 11% | 0% | 0% | 0% | 0% |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| documents-documents-adversarial_pellucid_incidents.md | documents | document | 26 | 4 | 100% |
| documents-documents-adversarial_quenby_suppliers.md | documents | document | 28 | 4 | 100% |
| documents-documents-it_services_corvane.md | documents | document | 129 | 11 | 100% |
| documents-documents-manufacturer_aldermoor.md | documents | document | 110 | 11 | 100% |
| documents-documents-structure_brackwater_distribution.md | documents | document | 66 | 7 | 100% |
| documents-documents-structure_lestrade_logistique_fr.md | documents | document | 63 | 7 | 100% |
| benchmarks-org-org.md | benchmarks | document | 13 | 31 | 85% |
| benchmarks-ssn-ssn.md | benchmarks | document | 22 | 41 | 100% |

### Gold Tree Reports

- benchmarks-org-org.md: `{"gold": "org.ttl", "source": "org.ttl", "format": "turtle", "concepts": 13, "relations": 31, "optional": 1, "maxDepth": 3, "unreachable": [], "classes": 14, "rootClasses": [], "objectProperties": 31, "individuals": 1, "ignoredAxioms": {"rdfs:comment": 223, "rdfs:isDefinedBy": 44, "owl:inverseOf": 16, "dct:modified": 10, "owl:disjointWith": 10, "dct:contributor": 9, "foaf:name": 9, "rdfs:subPropertyOf": 9, "foaf:mbox": 8, "rdf:first": 5, "rdf:rest": 5, "dct:title": 4, "individual assertion rdfs:comment": 4, "individual assertion skos:prefLabel": 3, "owl:equivalentClass": 2, "dct:created": 1, "`
- benchmarks-ssn-ssn.md: `{"gold": "ssn.ttl", "source": "ssn.ttl", "format": "turtle", "concepts": 22, "relations": 41, "optional": 2, "maxDepth": 2, "unreachable": [], "classes": 22, "rootClasses": [], "objectProperties": 36, "individuals": 2, "ignoredAxioms": {"rdfs:comment": 60, "rdfs:isDefinedBy": 57, "skos:definition": 57, "schema1:domainIncludes": 40, "owl:inverseOf": 35, "skos:example": 34, "schema1:rangeIncludes": 30, "owl:Restriction (unqualified cardinality)": 20, "owl:Restriction (complex property)": 9, "owl:onProperty": 9, "rdf:first": 8, "rdf:rest": 8, "owl:allValuesFrom": 7, "individual assertion dcterms:`

## Documents And OCR

OCR runs once per scanned document, before and apart from the model runs.

| Document | Format | Words | Pages | OCR deployment | OCR pages | OCR s | OCR EUR |
|---|---|---|---|---|---|---|---|
| adversarial_pellucid_incidents.md | md | 326 | - | - | - | 0.0 | 0.0000 |
| adversarial_quenby_suppliers.md | md | 378 | - | - | - | 0.0 | 0.0000 |
| it_services_corvane.md | md | 5090 | - | - | - | 0.0 | 0.0000 |
| manufacturer_aldermoor.md | md | 3510 | - | - | - | 0.0 | 0.0000 |
| structure_brackwater_distribution.md | md | 1574 | - | - | - | 0.0 | 0.0000 |
| structure_lestrade_logistique_fr.md | md | 1788 | - | - | - | 0.0 | 0.0000 |
| org.md | md | 4913 | - | - | - | 0.0 | 0.0000 |
| ssn.md | md | 7379 | - | - | - | 0.0 | 0.0000 |
