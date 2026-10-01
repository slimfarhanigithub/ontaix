# Teach Bake-Off Report

Started 2026-09-30T21:24:01+00:00. Spent 0.0718 EUR of a 0.30 EUR budget (estimate before the run: 0.02 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@none | eu_data_zone | 0.961 | 0.971 | 0.919 | 1.000 | 100% | 95% | 90% | 99% | 89% | 0 | 4 | 89% | 1 | 0 | 4 | 0.0718 | 8.7 | 15.4 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | documents:whole |
|---|---|
| gpt-6-sol@none | 97% / 89% / 0.072 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (2) | L2 (12) | L3 (19) | L4 (37) | L5 (4) |
|---|---|---|---|---|---|
| gpt-6-sol@none | 100% | 96% | 76% | 88% | 86% |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| documents-documents-structure_ostrava_mutual_claims.md | documents | document | 74 | 6 | 100% |

## Documents And OCR

OCR runs once per scanned document, before and apart from the model runs.

| Document | Format | Words | Pages | OCR deployment | OCR pages | OCR s | OCR EUR |
|---|---|---|---|---|---|---|---|
| structure_ostrava_mutual_claims.md | md | 1925 | - | - | - | 0.0 | 0.0000 |
