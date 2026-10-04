# Teach Bake-Off Report

Started 2026-10-04T14:59:50+00:00. Spent 0.1597 EUR of a 0.24 EUR budget (estimate before the run: 0.28 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@none | eu_data_zone | 1.010 | 1.000 | 1.032 | 1.000 | 100% | 100% | 100% | 100% | 100% | 0 | 0 | 106% | 0 | 0 | 12 | 0.1597 | 4.0 | 8.8 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | dataset:speech |
|---|---|
| gpt-6-sol@none | 100% / 100% / 0.160 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (12) | L2 (27) | L3 (32) | L4 (0) |
|---|---|---|---|---|
| gpt-6-sol@none | 114% | 102% | 103% | 0% |

### Screening Speech Comprehension

Each recording is sent sentence by sentence as `speech` in one session; its final drafts are scored against the gold tree. Parent at depth: expected concepts drafted under an accepted parent at the expected level. Verb: matched concepts with an accepted verb. Relation: expected relations drafted with an accepted verb. Attribute: expected taught attributes drafted on the right concept with an accepted value.

| Case | Configuration | Repeat | Sentences | Parent at depth | Verb | Relation | Attribute | Depth reached / gold | Invented | Missed |
|---|---|---|---|---|---|---|---|---|---|---|
| en-speech-demo-talk | gpt-6-sol@none | 0 | 2 | 0/0 | 0/0 | - | - | 0 / 0 | - | - |
| en-speech-five-kinds-then-fragments | gpt-6-sol@none | 0 | 3 | 9/9 | 9/9 | - | - | 3 / 3 | - | - |
| en-speech-kinds-then-badge | gpt-6-sol@none | 0 | 1 | 8/8 | 8/8 | 1/1 | - | 3 / 3 | - | - |
| en-speech-misheard-article-and-fragment | gpt-6-sol@none | 0 | 1 | 11/11 | 11/11 | 1/1 | - | 3 / 3 | - | - |
| en-speech-misheard-article-in-list | gpt-6-sol@none | 0 | 1 | 12/12 | 12/12 | 1/1 | - | 3 / 3 | - | - |
| en-speech-misheard-company-mid-sentence | gpt-6-sol@none | 0 | 1 | 12/12 | 12/12 | 1/1 | - | 3 / 3 | - | - |
| en-speech-misheard-title-in-list | gpt-6-sol@none | 0 | 2 | 8/8 | 8/8 | - | - | 3 / 3 | - | - |
| en-speech-serves-word-order | gpt-6-sol@none | 0 | 1 | 11/11 | 11/11 | 0/1 | - | 4 / 3 | - | - |

### Screening Timing Breakdown For gpt-6-sol@none

Milliseconds per stage over every parse of the run. `parse` is the request: `view` loads the ontology, `source` applies the gates and charges, `grammar` runs the rules, `model` is the whole model step, `drafts` builds the drafts and `turns` stores the session turns. `extraction` is the model step: `budget` and `reserve` check and reserve the budgets, `candidates`, `examples` and `context` build the prompt, `provider` is the whole model call and `provider_first_token` its time to the first answer fragment when streamed, `interpret` validates, grounds and maps the answer, `settle` records the cost; `harness` `gate` is the time a call waited for the harness's own concurrency gate, which the pipeline's `provider` stage includes. Token counts are per call.

| Clock | Stage | Parses | p50 | p90 | Max |
|---|---|---|---|---|---|
| harness | gate | 12 | 0 | 0 | 0 |
| extraction | budget | 12 | 3 | 5 | 5 |
| extraction | candidates | 12 | 0 | 1 | 1 |
| extraction | examples | 12 | 1 | 2 | 3 |
| extraction | learning | 12 | 0 | 0 | 0 |
| extraction | context | 12 | 0 | 1 | 1 |
| extraction | reserve | 12 | 4 | 10 | 69 |
| extraction | provider | 12 | 3348 | 7776 | 8750 |
| extraction | interpret | 12 | 14 | 33 | 34 |
| extraction | settle | 12 | 5 | 6 | 16 |
| extraction | total | 12 | 3378 | 7825 | 8863 |
| extraction | input_tokens | 12 | 8484 | 8822 | 8846 |
| extraction | output_tokens | 12 | 606 | 1176 | 1210 |
| parse | view | 12 | 12 | 47 | 48 |
| parse | source | 12 | 4 | 42 | 45 |
| parse | model | 12 | 3382 | 7831 | 8872 |
| parse | drafts | 12 | 0 | 0 | 0 |
| parse | turns | 12 | 7 | 22 | 36 |
| parse | learning | 12 | 0 | 0 | 0 |
| parse | total | 12 | 3410 | 7944 | 9000 |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| en-speech-misheard-title-in-list | dataset | speech | 8 | 0 | 88% |
| en-speech-misheard-article-and-fragment | dataset | speech | 11 | 1 | 91% |
| en-speech-five-kinds-then-fragments | dataset | speech | 9 | 0 | 100% |
| en-speech-kinds-then-badge | dataset | speech | 8 | 1 | 100% |
| en-speech-misheard-article-in-list | dataset | speech | 12 | 1 | 92% |
| en-speech-misheard-company-mid-sentence | dataset | speech | 12 | 1 | 92% |
| en-speech-serves-word-order | dataset | speech | 11 | 1 | 100% |
| en-speech-demo-talk | dataset | speech | 0 | 0 | 100% |
