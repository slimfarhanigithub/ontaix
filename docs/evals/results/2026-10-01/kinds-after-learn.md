# Teach Bake-Off Report

Started 2026-10-01T07:11:06+00:00. Spent 0.9245 EUR of a 1.70 EUR budget (estimate before the run: 1.67 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@none | eu_data_zone | 0.968 | 0.996 | 0.899 | 1.000 | 100% | 99% | 99% | 99% | 96% | 0 | 2 | 81% | 0 | 0 | 92 | 0.9245 | 4.8 | 8.3 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | dataset:speech | dataset:typed |
|---|---|---|
| gpt-6-sol@none | 99% / 95% / 0.650 | 100% / 100% / 0.275 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (59) | L2 (110) | L3 (70) | L4 (39) | L5 (7) | L6 (1) | L8 (0) |
|---|---|---|---|---|---|---|---|
| gpt-6-sol@none | 105% | 104% | 91% | 88% | 70% | 25% | 0% |

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
| en-speech-owner-live-amdaris | gpt-6-sol@none | 0 | 3 | 7/7 | 7/7 | 1/1 | - | 4 / 4 | - | - |
| en-speech-owner-live-employees | gpt-6-sol@none | 0 | 3 | 7/7 | 7/7 | 2/2 | - | 4 / 4 | - | - |
| en-speech-owner-live-inside-sales | gpt-6-sol@none | 0 | 1 | 2/2 | 2/2 | - | - | 2 / 2 | - | - |
| en-speech-owner-live-skills | gpt-6-sol@none | 0 | 2 | 8/8 | 8/8 | 1/1 | - | 3 / 3 | - | - |
| en-speech-product-structure | gpt-6-sol@none | 0 | 1 | 7/7 | 7/7 | - | - | 5 / 5 | - | - |
| en-speech-recording-billing-drilldown | gpt-6-sol@none | 0 | 6 | 8/8 | 8/8 | 5/5 | 2/2 | 5 / 4 | - | - |
| en-speech-recording-under-each | gpt-6-sol@none | 0 | 6 | 11/11 | 11/11 | - | - | 4 / 3 | - | - |
| en-speech-retail-monologue | gpt-6-sol@none | 0 | 1 | 21/33 | 29/31 | - | - | 8 / 5 | - | Formats, Tiers |
| fr-speech-chaine-banque | gpt-6-sol@none | 0 | 1 | 6/6 | 6/6 | - | - | 5 / 5 | - | - |
| fr-speech-fournisseur-division | gpt-6-sol@none | 0 | 1 | 6/6 | 6/6 | - | - | 3 / 3 | - | - |
| fr-speech-ils-elle | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 3 / 3 | - | - |
| fr-speech-offres-quatre-niveaux | gpt-6-sol@none | 0 | 1 | 5/5 | 5/5 | - | - | 4 / 4 | - | - |

### Screening Timing Breakdown For gpt-6-sol@none

Milliseconds per stage over every parse of the run. `parse` is the request: `view` loads the ontology, `source` applies the gates and charges, `grammar` runs the rules, `model` is the whole model step, `drafts` builds the drafts and `turns` stores the session turns. `extraction` is the model step: `budget` and `reserve` check and reserve the budgets, `candidates`, `examples` and `context` build the prompt, `provider` is the whole model call and `provider_first_token` its time to the first answer fragment when streamed, `interpret` validates, grounds and maps the answer, `settle` records the cost; `harness` `gate` is the time a call waited for the harness's own concurrency gate, which the pipeline's `provider` stage includes. Token counts are per call.

| Clock | Stage | Parses | p50 | p90 | Max |
|---|---|---|---|---|---|
| harness | gate | 92 | 13958 | 15377 | 26812 |
| extraction | budget | 89 | 3 | 13 | 71 |
| extraction | candidates | 89 | 0 | 1 | 2 |
| extraction | examples | 89 | 1 | 2 | 5 |
| extraction | learning | 89 | 0 | 0 | 0 |
| extraction | context | 89 | 0 | 1 | 4 |
| extraction | reserve | 89 | 4 | 24 | 92 |
| extraction | provider | 89 | 19079 | 21427 | 40026 |
| extraction | interpret | 89 | 3 | 6 | 126 |
| extraction | settle | 89 | 11 | 17 | 49 |
| extraction | total | 89 | 19105 | 21466 | 40058 |
| extraction | input_tokens | 89 | 8091 | 8293 | 8592 |
| extraction | output_tokens | 89 | 224 | 462 | 3065 |
| parse | view | 89 | 12 | 38 | 91 |
| parse | source | 89 | 4 | 14 | 63 |
| parse | model | 89 | 19109 | 21470 | 40063 |
| parse | drafts | 89 | 0 | 0 | 1 |
| parse | turns | 89 | 8 | 22 | 47 |
| parse | learning | 89 | 0 | 0 | 0 |
| parse | total | 89 | 19133 | 21493 | 40126 |
| parse | grammar | 27 | 0 | 1 | 2 |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| en-speech-owner-financial-services | dataset | speech | 8 | 5 | 100% |
| en-speech-owner-live-employees | dataset | speech | 7 | 2 | 100% |
| en-speech-owner-live-inside-sales | dataset | speech | 2 | 0 | 100% |
| en-speech-owner-live-amdaris | dataset | speech | 7 | 1 | 100% |
| en-speech-owner-live-skills | dataset | speech | 8 | 1 | 100% |
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
| en-text-owner-live-sales-steps | dataset | text | 10 | 9 | 100% |
| en-text-owner-live-long-steps | dataset | text | 7 | 6 | 100% |
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
