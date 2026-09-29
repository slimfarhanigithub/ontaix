# Public Ontology Benchmarks

Each folder pairs a published ontology (the gold tree) with the prose of its specification (the document the models read). All files were retrieved on 2026-09-29. The specification HTML is not stored; for the W3C and GoodRelations pairs `<name>.md` is produced from it with `uv run python -m evals.html_to_text <spec.html> <name>.md`, which keeps headings and prose definitions and drops navigation, the table of contents, code blocks and element metadata boxes.

Size cap: a document is at most 100 KiB and an ontology at most 250 KiB. A longer document keeps the sections that define the classes and properties; the trimmed ones are listed under Trimming.

| Folder | Ontology | Specification | Licence |
|---|---|---|---|
| `org/` | `org.ttl` from https://www.w3.org/ns/org.ttl (W3C Organization Ontology, version 0.8) | https://www.w3.org/TR/vocab-org/ (W3C Recommendation, 16 January 2014, https://www.w3.org/TR/2014/REC-vocab-org-20140116/) | W3C Software and Document License, https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document |
| `goodrelations/` | `goodrelations.owl` from http://purl.org/goodrelations/v1.owl (GoodRelations Vocabulary for E-Commerce, Martin Hepp) | http://purl.org/goodrelations/v1.html (GoodRelations Language Reference, served from http://www.heppnetz.de/ontologies/goodrelations/v1.html) | Creative Commons Attribution-ShareAlike 3.0, https://creativecommons.org/licenses/by-sa/3.0/ |
| `prov-o/` | `prov-o.ttl` from https://www.w3.org/ns/prov-o.ttl (PROV-O: The PROV Ontology) | https://www.w3.org/TR/prov-o/ (W3C Recommendation, 30 April 2013, https://www.w3.org/TR/2013/REC-prov-o-20130430/) | W3C Software and Document License, https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document |
| `dcat/` | `dcat3.ttl` from https://www.w3.org/ns/dcat3.ttl (Data Catalog Vocabulary, version 3) | https://www.w3.org/TR/vocab-dcat-3/ (W3C Recommendation, 22 August 2024) | W3C Software and Document License, https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document |
| `ssn/` | `ssn.ttl` is https://www.w3.org/ns/sosa/ followed by https://www.w3.org/ns/ssn/ (both fetched as Turtle, joined unchanged into one Turtle file so one gold tree covers the SOSA core and SSN) | https://www.w3.org/TR/vocab-ssn/ (Semantic Sensor Network Ontology, W3C Recommendation, 19 October 2017, https://www.w3.org/TR/2017/REC-vocab-ssn-20171019/) | W3C Software and Document License, https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document |
| `time/` | `time.ttl` from https://www.w3.org/2006/time.ttl (Time Ontology in OWL) | https://www.w3.org/TR/2017/REC-owl-time-20171019/ (W3C Recommendation, 19 October 2017; the later Candidate Recommendation Draft at https://www.w3.org/TR/owl-time/ defines the same classes) | W3C Software and Document License, https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document |
| `valueflows/` | `valueflows.jsonld` is `mkdocs/docs/specification/all_vf.jsonld` from https://lab.allmende.io/valueflows/valueflows (commit 43701c13f64cb1fded60d7953989b5c9e23968ed, the source of the specification pages of https://www.valueflo.ws/) | The ValueFlows documentation at https://www.valueflo.ws/, from the Markdown sources in `mkdocs/docs/` of the same commit | Creative Commons Attribution-ShareAlike 4.0, https://creativecommons.org/licenses/by-sa/4.0/ |

Attribution: the W3C Organization Ontology, PROV-O, DCAT 3, SOSA/SSN, the Time Ontology in OWL and their Recommendations are Copyright World Wide Web Consortium (SOSA/SSN and OWL-Time jointly with the Open Geospatial Consortium); GoodRelations and its Language Reference are by Martin Hepp; ValueFlows and its documentation are by the Valueflows contributors listed at https://valueflo.ws/introduction/contributors.html. `goodrelations/goodrelations.md` is an adaptation (prose extracted from the Language Reference) and is shared under the same CC BY-SA 3.0 licence. `valueflows/valueflows.md` is an adaptation (prose extracted from the documentation) and is shared under the same CC BY-SA 4.0 licence.

## Business-Process Pair

ValueFlows is the business-process benchmark. It models economic processes with the REA pattern (resources, events, agents) and input-process-output flows, and covers plans, commitments, intents, recipes, exchanges and transfers. Its documentation is hand-written prose, independent of the vocabulary file. FIBO (MIT) was the first choice, but its Business Process modules (`BP/SecuritiesIssuance/IssuanceProcess`, `BP/Process/FinancialContextAndProcess`) have no published prose document: the FIBO Viewer renders the ontology's own annotations, so a document built from it would restate the gold.

`valueflows.md` joins these pages of `mkdocs/docs/`, in the site's order, as one Markdown file: `introduction/core.md`, `specification/model-text.md`, then `concepts/` agents, resources, flows, actions, processes, transfers, exchanges, proposals, plan, estimates, recipes, scoping, accounting and ecology. Fenced code blocks, images, HTML tags and bare URLs are removed and link text is kept.

## Trimming

- `dcat/dcat3.md` keeps sections 1 to 6 (introduction, vocabulary overview and the vocabulary specification of every class and property) and drops sections 7 to 15 (inverse properties, identifiers, licences, time and space, versioning, dataset series, citation, quality) and the appendices. The full text is 156 KiB.
- `ssn/ssn.md` keeps sections 1 to 4 (the SOSA and SSN core classes and properties, which `ssn.ttl` defines) and drops section 5 (the System Capabilities and Sample Relations modules, which are separate ontologies) and section 6 onwards (alignment modules and appendices). The full text is 94 KiB.
- `valueflows/valueflows.md` leaves out the concept pages on classification, location and the concepts overview, which fall past the size cap. The examples, algorithms and FAQ pages are not included.

## Pairing

The bake-off pairs files by name inside a folder: `<name>.(ttl|owl|rdf|jsonld|...)` is the gold tree and `<name>.md` the document. `<name>.expected.yaml` holds the company name the models are told (`company:`). Each folder yields one case, `benchmarks-<folder>-<name>.md`, found by `evals.case_sources.benchmark_folders`.

## Learn and Test Split

`split-additions.json` assigns the pairs after `org` and `goodrelations`: `prov-o` and `dcat` to LEARN; `ssn`, `time` and `valueflows` to TEST.
