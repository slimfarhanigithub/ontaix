# Teach Bake-Off Report

Started 2026-09-30T21:46:46+00:00. Spent 0.7724 EUR of a 37.40 EUR budget (estimate before the run: 1.41 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@none | eu_data_zone | 0.957 | 0.985 | 0.883 | 1.000 | 98% | 98% | 99% | 99% | 96% | 5 | 4 | 78% | 0 | 0 | 79 | 0.7724 | 4.1 | 6.3 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | dataset:speech | dataset:typed |
|---|---|---|
| gpt-6-sol@none | 97% / 94% / 0.537 | 100% / 100% / 0.235 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (39) | L2 (101) | L3 (66) | L4 (31) | L5 (7) | L6 (1) | L8 (0) |
|---|---|---|---|---|---|---|---|
| gpt-6-sol@none | 106% | 104% | 90% | 83% | 63% | 25% | 0% |

### Screening Speech Comprehension

Each recording is sent sentence by sentence as `speech` in one session; its final drafts are scored against the gold tree. Parent at depth: expected concepts drafted under an accepted parent at the expected level. Verb: matched concepts with an accepted verb. Relation: expected relations drafted with an accepted verb. Attribute: expected taught attributes drafted on the right concept with an accepted value.

| Case | Configuration | Repeat | Sentences | Parent at depth | Verb | Relation | Attribute | Depth reached / gold | Invented | Missed |
|---|---|---|---|---|---|---|---|---|---|---|
| en-speech-adr-owner-spoken | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 2 / 2 | - | - |
| en-speech-correction-i-meant | gpt-6-sol@none | 0 | 1 | 3/4 | 4/4 | - | - | 2 / 2 | - | - |
| en-speech-cross-domain-it | gpt-6-sol@none | 0 | 1 | 0/0 | 0/0 | 2/2 | - | 0 / 0 | - | - |
| en-speech-customer-also-supplier | gpt-6-sol@none | 0 | 1 | 5/5 | 5/5 | - | - | 3 / 3 | - | - |
| en-speech-false-starts | gpt-6-sol@none | 0 | 1 | 3/3 | 3/3 | - | - | 3 / 3 | - | - |
| en-speech-grouping-offerings | gpt-6-sol@none | 0 | 1 | 6/6 | 6/6 | - | - | 4 / 4 | - | - |
| en-speech-grouping-teams-corrected | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 3 / 2 | - | - |
| en-speech-hesitation-month-end | gpt-6-sol@none | 0 | 1 | 3/3 | 3/3 | - | - | 3 / 3 | - | - |
| en-speech-narration-dcat-catalogs | gpt-6-sol@none | 0 | 6 | 9/9 | 9/9 | 1/1 | - | 5 / 5 | - | - |
| en-speech-narration-goodrelations-offerings | gpt-6-sol@none | 0 | 7 | 13/13 | 13/13 | 1/1 | - | 3 / 3 | - | - |
| en-speech-narration-prov-o-starting-points | gpt-6-sol@none | 0 | 7 | 14/14 | 14/14 | 3/3 | - | 3 / 3 | - | - |
| en-speech-owner-adnoc-client | gpt-6-sol@none | 0 | 1 | 10/10 | 10/10 | - | - | 4 / 4 | - | - |
| en-speech-owner-financial-services | gpt-6-sol@none | 0 | 6 | 8/8 | 8/8 | 5/5 | 2/2 | 5 / 4 | - | - |
| en-speech-product-structure | gpt-6-sol@none | 0 | 1 | 7/7 | 7/7 | - | - | 5 / 5 | - | - |
| en-speech-recording-billing-drilldown | gpt-6-sol@none | 0 | 6 | 8/8 | 8/8 | 5/5 | 2/2 | 5 / 4 | - | - |
| en-speech-recording-under-each | gpt-6-sol@none | 0 | 6 | 11/11 | 11/11 | - | - | 4 / 3 | - | - |
| en-speech-retail-monologue | gpt-6-sol@none | 0 | 1 | 21/33 | 28/31 | - | - | 8 / 5 | Store, Gold members, Collection, Product range, Style | Formats, Tiers |
| fr-speech-chaine-banque | gpt-6-sol@none | 0 | 1 | 4/6 | 4/4 | - | - | 3 / 5 | - | Analyse de risque, Offre de prêt |
| fr-speech-fournisseur-division | gpt-6-sol@none | 0 | 1 | 6/6 | 6/6 | - | - | 3 / 3 | - | - |
| fr-speech-ils-elle | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 3 / 3 | - | - |
| fr-speech-offres-quatre-niveaux | gpt-6-sol@none | 0 | 1 | 5/5 | 5/5 | - | - | 4 / 4 | - | - |

### Screening Timing Breakdown For gpt-6-sol@none

Milliseconds per stage over every parse of the run. `parse` is the request: `view` loads the ontology, `source` applies the gates and charges, `grammar` runs the rules, `model` is the whole model step, `drafts` builds the drafts and `turns` stores the session turns. `extraction` is the model step: `budget` and `reserve` check and reserve the budgets, `candidates`, `examples` and `context` build the prompt, `provider` is the whole model call and `provider_first_token` its time to the first answer fragment when streamed, `interpret` validates, grounds and maps the answer, `settle` records the cost. Token counts are per call.

| Clock | Stage | Parses | p50 | p90 | Max |
|---|---|---|---|---|---|
| extraction | budget | 78 | 2 | 3 | 46 |
| extraction | candidates | 78 | 0 | 1 | 9 |
| extraction | examples | 78 | 1 | 1 | 3 |
| extraction | context | 78 | 0 | 0 | 0 |
| extraction | reserve | 78 | 2 | 3 | 6 |
| extraction | provider | 78 | 8681 | 10020 | 28281 |
| extraction | interpret | 78 | 2 | 7 | 124 |
| extraction | settle | 78 | 6 | 12 | 21 |
| extraction | total | 78 | 8694 | 10037 | 28293 |
| extraction | input_tokens | 78 | 7706 | 7917 | 8224 |
| extraction | output_tokens | 78 | 218 | 385 | 3090 |
| parse | view | 78 | 7 | 11 | 21 |
| parse | source | 78 | 2 | 3 | 39 |
| parse | model | 78 | 8696 | 10038 | 28296 |
| parse | drafts | 78 | 0 | 0 | 1 |
| parse | turns | 78 | 4 | 8 | 34 |
| parse | total | 78 | 8715 | 10053 | 28308 |
| parse | grammar | 25 | 0 | 1 | 1 |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| en-speech-owner-financial-services | dataset | speech | 8 | 5 | 100% |
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
