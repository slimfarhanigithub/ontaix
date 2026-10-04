# Teach Bake-Off Report

Started 2026-10-04T14:00:53+00:00. Spent 0.3025 EUR of a 0.60 EUR budget (estimate before the run: 0.33 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@none | eu_data_zone | 0.997 | 0.996 | 0.996 | 1.000 | 100% | 100% | 98% | 100% | 98% | 0 | 0 | 99% | 0 | 0 | 42 | 0.3025 | 4.7 | 7.6 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | dataset:typed |
|---|---|
| gpt-6-sol@none | 100% / 98% / 0.302 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (14) | L2 (30) | L3 (12) | L4 (5) | L5 (2) | L6 (1) |
|---|---|---|---|---|---|---|
| gpt-6-sol@none | 96% | 98% | 100% | 100% | 100% | 100% |

### Screening Timing Breakdown For gpt-6-sol@none

Milliseconds per stage over every parse of the run. `parse` is the request: `view` loads the ontology, `source` applies the gates and charges, `grammar` runs the rules, `model` is the whole model step, `drafts` builds the drafts and `turns` stores the session turns. `extraction` is the model step: `budget` and `reserve` check and reserve the budgets, `candidates`, `examples` and `context` build the prompt, `provider` is the whole model call and `provider_first_token` its time to the first answer fragment when streamed, `interpret` validates, grounds and maps the answer, `settle` records the cost; `harness` `gate` is the time a call waited for the harness's own concurrency gate, which the pipeline's `provider` stage includes. Token counts are per call.

| Clock | Stage | Parses | p50 | p90 | Max |
|---|---|---|---|---|---|
| harness | gate | 42 | 0 | 0 | 0 |
| extraction | budget | 32 | 3 | 4 | 6 |
| extraction | candidates | 32 | 0 | 0 | 0 |
| extraction | examples | 32 | 1 | 1 | 2 |
| extraction | learning | 32 | 0 | 0 | 0 |
| extraction | context | 32 | 0 | 0 | 0 |
| extraction | reserve | 32 | 3 | 4 | 4 |
| extraction | provider | 32 | 4697 | 25337 | 64864 |
| extraction | interpret | 32 | 1 | 4 | 10 |
| extraction | settle | 32 | 4 | 7 | 10 |
| extraction | total | 32 | 4708 | 25346 | 64878 |
| extraction | input_tokens | 32 | 7959 | 8197 | 8246 |
| extraction | output_tokens | 32 | 192 | 279 | 535 |
| parse | view | 32 | 10 | 15 | 31 |
| parse | source | 32 | 3 | 4 | 32 |
| parse | grammar | 32 | 0 | 1 | 1 |
| parse | model | 32 | 4710 | 25349 | 64881 |
| parse | drafts | 32 | 0 | 0 | 0 |
| parse | turns | 32 | 5 | 6 | 11 |
| parse | learning | 32 | 0 | 0 | 0 |
| parse | total | 32 | 4735 | 25363 | 64901 |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
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
| fr-text-adr-deux-phrases | dataset | text | 4 | 0 | 100% |
| fr-text-reutilisation-ligne | dataset | text | 2 | 0 | 100% |
| fr-text-inter-domaines | dataset | text | 0 | 2 | 100% |
| fr-text-marques-ecart-compte | dataset | text | 4 | 0 | 100% |
| en-text-role-partner-and-supplier | dataset | text | 4 | 0 | 100% |
| en-text-role-vendor-existing-that | dataset | text | 3 | 0 | 100% |
| en-text-subsidiary-which-object | dataset | text | 3 | 0 | 100% |
| en-text-supplier-e-commerce | dataset | text | 3 | 0 | 100% |
| fr-text-client-filiales-qui | dataset | text | 6 | 0 | 100% |
