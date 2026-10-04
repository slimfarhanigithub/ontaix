# Teach Bake-Off Report

Started 2026-10-04T14:11:21+00:00. Spent 0.9016 EUR of a 1.30 EUR budget (estimate before the run: 1.56 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@none | eu_data_zone | 0.988 | 0.983 | 0.987 | 1.000 | 97% | 99% | 100% | 100% | 100% | 6 | 3 | 99% | 0 | 0 | 98 | 0.9016 | 4.9 | 7.8 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | dataset:speech | dataset:typed |
|---|---|---|
| gpt-6-sol@none | 97% / 100% / 0.584 | 99% / 98% / 0.317 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (45) | L2 (91) | L3 (52) | L4 (12) | L5 (6) | L6 (2) | L7 (1) |
|---|---|---|---|---|---|---|---|
| gpt-6-sol@none | 99% | 96% | 98% | 100% | 100% | 100% | 100% |

### Screening Speech Comprehension

Each recording is sent sentence by sentence as `speech` in one session; its final drafts are scored against the gold tree. Parent at depth: expected concepts drafted under an accepted parent at the expected level. Verb: matched concepts with an accepted verb. Relation: expected relations drafted with an accepted verb. Attribute: expected taught attributes drafted on the right concept with an accepted value.

| Case | Configuration | Repeat | Sentences | Parent at depth | Verb | Relation | Attribute | Depth reached / gold | Invented | Missed |
|---|---|---|---|---|---|---|---|---|---|---|
| en-speech-chain-bank | gpt-6-sol@none | 0 | 1 | 6/6 | 5/6 | - | - | 5 / 5 | - | - |
| en-speech-chain-seven-levels | gpt-6-sol@none | 0 | 1 | 11/11 | 11/11 | - | - | 7 / 7 | - | - |
| en-speech-correction-lines | gpt-6-sol@none | 0 | 1 | 5/5 | 5/5 | - | - | 2 / 2 | - | - |
| en-speech-cross-domain-payroll | gpt-6-sol@none | 0 | 1 | 1/1 | 1/1 | 2/2 | - | 3 / 3 | - | - |
| en-speech-customer-divisions-correction | gpt-6-sol@none | 0 | 1 | 6/6 | 6/6 | - | - | 4 / 4 | - | - |
| en-speech-fibre-order | gpt-6-sol@none | 0 | 1 | 5/5 | 5/5 | - | - | 4 / 4 | - | - |
| en-speech-grouping-count-corrected | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 2 / 2 | - | - |
| en-speech-is-a-elliptical | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 2 / 2 | - | - |
| en-speech-it-relations | gpt-6-sol@none | 0 | 1 | 0/0 | 0/0 | 1/2 | - | 0 / 0 | Orders | - |
| en-speech-narration-org-structure | gpt-6-sol@none | 0 | 7 | 9/9 | 9/9 | 1/2 | - | 3 / 3 | - | - |
| en-speech-narration-ssn-observations | gpt-6-sol@none | 0 | 7 | 12/12 | 12/12 | 2/3 | - | 3 / 3 | - | - |
| en-speech-narration-valueflows-processes | gpt-6-sol@none | 0 | 8 | 12/12 | 12/12 | 3/3 | - | 3 / 2 | Economic events, Economic event | - |
| en-speech-question-aside | gpt-6-sol@none | 0 | 1 | 3/3 | 3/3 | - | - | 2 / 2 | - | - |
| en-speech-recording-correction | gpt-6-sol@none | 0 | 4 | 4/4 | 4/4 | - | - | 3 / 3 | Travel claims | - |
| en-speech-recording-depot | gpt-6-sol@none | 0 | 4 | 6/6 | 6/6 | - | - | 4 / 4 | - | - |
| en-speech-run-on-they | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 3 / 3 | Logistics company | - |
| en-speech-these-policies | gpt-6-sol@none | 0 | 1 | 1/4 | 1/1 | - | - | 1 / 2 | - | Home, Motor, Travel |
| fr-speech-enregistrement-atelier | gpt-6-sol@none | 0 | 3 | 4/4 | 4/4 | - | - | 3 / 3 | - | - |
| fr-speech-est-un-type-de | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 2 / 2 | - | - |
| fr-speech-inter-domaines-sla | gpt-6-sol@none | 0 | 1 | 2/2 | 2/2 | 1/1 | - | 3 / 3 | - | - |
| fr-speech-urgences-correction | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 3 / 3 | - | - |

### Screening Timing Breakdown For gpt-6-sol@none

Milliseconds per stage over every parse of the run. `parse` is the request: `view` loads the ontology, `source` applies the gates and charges, `grammar` runs the rules, `model` is the whole model step, `drafts` builds the drafts and `turns` stores the session turns. `extraction` is the model step: `budget` and `reserve` check and reserve the budgets, `candidates`, `examples` and `context` build the prompt, `provider` is the whole model call and `provider_first_token` its time to the first answer fragment when streamed, `interpret` validates, grounds and maps the answer, `settle` records the cost; `harness` `gate` is the time a call waited for the harness's own concurrency gate, which the pipeline's `provider` stage includes. Token counts are per call.

| Clock | Stage | Parses | p50 | p90 | Max |
|---|---|---|---|---|---|
| harness | gate | 98 | 2677 | 6277 | 8120 |
| extraction | budget | 85 | 3 | 4 | 18 |
| extraction | candidates | 85 | 0 | 1 | 2 |
| extraction | examples | 85 | 1 | 1 | 3 |
| extraction | learning | 85 | 0 | 0 | 0 |
| extraction | context | 85 | 0 | 0 | 1 |
| extraction | reserve | 85 | 3 | 4 | 60 |
| extraction | provider | 85 | 9414 | 17425 | 185985 |
| extraction | interpret | 85 | 2 | 7 | 28 |
| extraction | settle | 85 | 8 | 11 | 15 |
| extraction | total | 85 | 9438 | 17442 | 186000 |
| extraction | input_tokens | 85 | 8487 | 8824 | 8984 |
| extraction | output_tokens | 85 | 213 | 496 | 1204 |
| parse | view | 85 | 8 | 14 | 49 |
| parse | source | 85 | 3 | 4 | 55 |
| parse | model | 85 | 9441 | 17444 | 186003 |
| parse | drafts | 85 | 0 | 0 | 0 |
| parse | turns | 85 | 5 | 13 | 36 |
| parse | learning | 85 | 0 | 0 | 0 |
| parse | total | 85 | 9455 | 17461 | 186021 |
| parse | grammar | 32 | 0 | 1 | 1 |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| en-speech-narration-valueflows-processes | dataset | speech | 12 | 3 | 100% |
| en-speech-narration-org-structure | dataset | speech | 9 | 2 | 100% |
| en-speech-narration-ssn-observations | dataset | speech | 12 | 3 | 100% |
| en-text-grouping-product-lines | dataset | text | 5 | 0 | 100% |
| en-text-descriptive-regions | dataset | text | 3 | 0 | 100% |
| en-text-reuse-production-line | dataset | text | 2 | 0 | 100% |
| en-text-already-known-then-new | dataset | text | 1 | 0 | 100% |
| en-text-already-known-only | dataset | text | 0 | 0 | 100% |
| en-text-is-a-new-parent | dataset | text | 3 | 0 | 100% |
| en-text-cross-domain-quality-finance | dataset | text | 0 | 2 | 100% |
| en-text-cross-domain-order-flow | dataset | text | 0 | 2 | 100% |
| en-text-chain-six-levels | dataset | text | 6 | 0 | 100% |
| en-text-back-reference-they-it | dataset | text | 4 | 0 | 100% |
| en-text-descriptive-topics | dataset | text | 2 | 0 | 100% |
| en-text-plural-reuse-passive | dataset | text | 1 | 0 | 100% |
| en-text-chain-across-turns | dataset | text | 6 | 0 | 100% |
| en-text-correction-typed | dataset | text | 2 | 0 | 100% |
| en-speech-correction-lines | dataset | speech | 5 | 0 | 100% |
| en-speech-run-on-they | dataset | speech | 4 | 0 | 100% |
| en-speech-chain-bank | dataset | speech | 6 | 0 | 100% |
| en-speech-question-aside | dataset | speech | 3 | 0 | 100% |
| en-speech-grouping-count-corrected | dataset | speech | 4 | 0 | 100% |
| en-speech-is-a-elliptical | dataset | speech | 4 | 0 | 100% |
| en-speech-chain-seven-levels | dataset | speech | 11 | 0 | 100% |
| en-speech-it-relations | dataset | speech | 0 | 2 | 100% |
| en-speech-these-policies | dataset | speech | 4 | 0 | 100% |
| en-speech-cross-domain-payroll | dataset | speech | 1 | 2 | 100% |
| en-speech-fibre-order | dataset | speech | 5 | 0 | 100% |
| fr-text-adr-deux-phrases | dataset | text | 4 | 0 | 100% |
| fr-text-reutilisation-ligne | dataset | text | 2 | 0 | 100% |
| fr-text-inter-domaines | dataset | text | 0 | 2 | 100% |
| fr-text-marques-ecart-compte | dataset | text | 4 | 0 | 100% |
| fr-speech-urgences-correction | dataset | speech | 4 | 0 | 100% |
| fr-speech-est-un-type-de | dataset | speech | 4 | 0 | 100% |
| fr-speech-inter-domaines-sla | dataset | speech | 2 | 1 | 100% |
| en-text-role-partner-and-supplier | dataset | text | 4 | 0 | 100% |
| en-text-role-vendor-existing-that | dataset | text | 3 | 0 | 100% |
| en-text-subsidiary-which-object | dataset | text | 3 | 0 | 100% |
| en-speech-customer-divisions-correction | dataset | speech | 6 | 0 | 100% |
| en-text-supplier-e-commerce | dataset | text | 3 | 0 | 100% |
| fr-text-client-filiales-qui | dataset | text | 6 | 0 | 100% |
| en-speech-recording-depot | dataset | speech | 6 | 0 | 100% |
| en-speech-recording-correction | dataset | speech | 4 | 0 | 100% |
| fr-speech-enregistrement-atelier | dataset | speech | 4 | 0 | 100% |
