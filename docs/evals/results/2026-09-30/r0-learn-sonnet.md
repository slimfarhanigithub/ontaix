# Teach Bake-Off Report

Started 2026-09-29T21:52:03+00:00. Spent 1.3229 EUR of a 5.00 EUR budget (estimate before the run: 3.08 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | claude-sonnet-5@none | global | 0.915 | 0.946 | 0.805 | 1.000 | 94% | 89% | 92% | 99% | 82% | 14 | 26 | 72% | 1 | 0 | 78 | 1.3229 | 4.1 | 7.1 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | dataset:speech | dataset:typed |
|---|---|---|
| claude-sonnet-5@none | 90% / 75% / 0.903 | 93% / 92% / 0.420 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (35) | L2 (96) | L3 (65) | L4 (33) | L5 (7) | L6 (1) |
|---|---|---|---|---|---|---|
| claude-sonnet-5@none | 71% | 91% | 69% | 41% | 60% | 100% |

### Screening Speech Comprehension

Each recording is sent sentence by sentence as `speech` in one session; its final drafts are scored against the gold tree. Parent at depth: expected concepts drafted under an accepted parent at the expected level. Verb: matched concepts with an accepted verb. Relation: expected relations drafted with an accepted verb. Attribute: expected taught attributes drafted on the right concept with an accepted value.

| Case | Configuration | Repeat | Sentences | Parent at depth | Verb | Relation | Attribute | Depth reached / gold | Invented | Missed |
|---|---|---|---|---|---|---|---|---|---|---|
| en-speech-adr-owner-spoken | claude-sonnet-5@none | 0 | 1 | 4/4 | 4/4 | - | - | 2 / 2 | - | - |
| en-speech-correction-i-meant | claude-sonnet-5@none | 0 | 1 | 3/4 | 4/4 | - | - | 2 / 2 | - | - |
| en-speech-cross-domain-it | claude-sonnet-5@none | 0 | 1 | 0/0 | 0/0 | 2/2 | - | 0 / 0 | - | - |
| en-speech-customer-also-supplier | claude-sonnet-5@none | 0 | 1 | 5/5 | 5/5 | - | - | 3 / 3 | - | - |
| en-speech-false-starts | claude-sonnet-5@none | 0 | 1 | 3/3 | 3/3 | - | - | 3 / 3 | - | - |
| en-speech-grouping-offerings | claude-sonnet-5@none | 0 | 1 | 6/6 | 6/6 | - | - | 4 / 4 | - | - |
| en-speech-grouping-teams-corrected | claude-sonnet-5@none | 0 | 1 | 4/4 | 4/4 | - | - | 3 / 2 | - | - |
| en-speech-hesitation-month-end | claude-sonnet-5@none | 0 | 1 | 3/3 | 3/3 | - | - | 3 / 3 | - | - |
| en-speech-narration-dcat-catalogs | claude-sonnet-5@none | 0 | 6 | 6/9 | 7/7 | 1/1 | - | 3 / 5 | - | Relationship, Role |
| en-speech-narration-goodrelations-offerings | claude-sonnet-5@none | 0 | 7 | 3/13 | 12/13 | 1/1 | - | 4 / 3 | - | - |
| en-speech-narration-prov-o-starting-points | claude-sonnet-5@none | 0 | 7 | 3/14 | 14/14 | 3/3 | - | 4 / 3 | - | - |
| en-speech-owner-adnoc-client | claude-sonnet-5@none | 0 | 1 | 0/10 | 1/1 | - | - | 2 / 4 | So um adnoc is a client of insight uh that, Multiple subsidiaries including l&s gas sour gas offshore onshore xrg, So um adnoc is a client of insight uh that | Client, ADNOC, Subsidiaries, L&S, Gas, Sour Gas, Offshore, Onshore, XRG |
| en-speech-product-structure | claude-sonnet-5@none | 0 | 1 | 7/7 | 7/7 | - | - | 5 / 5 | - | - |
| en-speech-recording-billing-drilldown | claude-sonnet-5@none | 0 | 6 | 5/8 | 8/8 | 4/5 | 1/2 | 3 / 4 | - | - |
| en-speech-recording-under-each | claude-sonnet-5@none | 0 | 6 | 10/11 | 10/10 | - | - | 4 / 4 | - | Cellar |
| en-speech-retail-monologue | claude-sonnet-5@none | 0 | 1 | 18/33 | 23/25 | - | - | 4 / 5 | Store, Product range, Style | Receiving, Put-away, Quality sampling, Picking, Packing, Free delivery, Buying and merchandising, Customers |
| fr-speech-chaine-banque | claude-sonnet-5@none | 0 | 1 | 4/6 | 4/4 | - | - | 3 / 5 | - | Analyse de risque, Offre de prêt |
| fr-speech-fournisseur-division | claude-sonnet-5@none | 0 | 1 | 6/6 | 6/6 | - | - | 3 / 3 | - | - |
| fr-speech-ils-elle | claude-sonnet-5@none | 0 | 1 | 4/4 | 4/4 | - | - | 3 / 3 | - | - |
| fr-speech-offres-quatre-niveaux | claude-sonnet-5@none | 0 | 1 | 5/5 | 5/5 | - | - | 4 / 4 | - | - |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| en-speech-narration-goodrelations-offerings | dataset | speech | 13 | 1 | 100% |
| en-speech-narration-prov-o-starting-points | dataset | speech | 14 | 3 | 100% |
| en-speech-narration-dcat-catalogs | dataset | speech | 9 | 1 | 100% |
| en-speech-recording-billing-drilldown | dataset | speech | 8 | 5 | 100% |
| en-speech-recording-under-each | dataset | speech | 11 | 0 | 100% |
| en-text-adr-owner-sentences | dataset | text | 4 | 0 | 100% |
| en-text-grouping-offerings | dataset | text | 4 | 0 | 100% |
| en-text-descriptive-count-mismatch | dataset | text | 3 | 0 | 100% |
| en-text-is-a-existing-parent | dataset | text | 2 | 0 | 100% |
| en-text-chain-five-levels | dataset | text | 5 | 0 | 100% |
| en-text-back-reference-those | dataset | text | 2 | 0 | 100% |
| en-text-verb-variety | dataset | text | 3 | 0 | 100% |
| en-text-grouping-channels | dataset | text | 4 | 0 | 100% |
| en-text-grouping-then-descriptive | dataset | text | 6 | 0 | 100% |
| en-text-reuse-and-cross-link | dataset | text | 2 | 1 | 100% |
| en-text-descriptive-regions-minimal-pair | dataset | text | 3 | 0 | 100% |
| en-speech-adr-owner-spoken | dataset | speech | 4 | 0 | 100% |
| en-speech-grouping-offerings | dataset | speech | 6 | 0 | 100% |
| en-speech-correction-i-meant | dataset | speech | 4 | 0 | 100% |
| en-speech-cross-domain-it | dataset | speech | 0 | 2 | 100% |
| en-speech-false-starts | dataset | speech | 3 | 0 | 100% |
| en-speech-grouping-teams-corrected | dataset | speech | 4 | 0 | 100% |
| en-speech-product-structure | dataset | speech | 7 | 0 | 100% |
| en-speech-hesitation-month-end | dataset | speech | 3 | 0 | 100% |
| en-speech-retail-monologue | dataset | speech | 33 | 0 | 100% |
| fr-text-regroupement-offres | dataset | text | 4 | 0 | 100% |
| fr-text-regions-ecart-compte | dataset | text | 3 | 0 | 100% |
| fr-text-est-un-type-de | dataset | text | 2 | 0 | 100% |
| fr-text-chaine-six-niveaux | dataset | text | 6 | 0 | 100% |
| fr-text-deja-connu | dataset | text | 2 | 0 | 100% |
| fr-speech-offres-quatre-niveaux | dataset | speech | 5 | 0 | 100% |
| fr-speech-chaine-banque | dataset | speech | 6 | 0 | 100% |
| fr-speech-ils-elle | dataset | speech | 4 | 0 | 100% |
| en-text-owner-adnoc-client | dataset | text | 10 | 0 | 100% |
| en-speech-owner-adnoc-client | dataset | speech | 10 | 0 | 100% |
| en-text-role-customer-of | dataset | text | 2 | 0 | 100% |
| en-text-division-rnd-that | dataset | text | 4 | 0 | 100% |
| en-text-partner-att-that | dataset | text | 4 | 0 | 100% |
| en-speech-customer-also-supplier | dataset | speech | 5 | 0 | 100% |
| en-text-client-subsidiaries-existing | dataset | text | 4 | 0 | 100% |
| fr-speech-fournisseur-division | dataset | speech | 6 | 0 | 100% |
| fr-text-partenaire-sa-e-commerce | dataset | text | 3 | 0 | 100% |
