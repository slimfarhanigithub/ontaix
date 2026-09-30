# Teach Bake-Off Report

Started 2026-09-29T22:50:20+00:00. Spent 1.4755 EUR of a 2.00 EUR budget (estimate before the run: 1.21 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@none | eu_data_zone | 0.656 | 0.582 | 0.552 | 1.000 | 38% | 97% | 68% | 89% | 24% | 118 | 2 | 13% | 1 | 0 | 166 | 1.4755 | 1.8 | 4.2 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | documents:sentences |
|---|---|
| gpt-6-sol@none | 55% / 24% / 1.476 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (2) | L2 (12) | L3 (19) | L4 (37) | L5 (4) | L6 (0) | L7 (0) | L8 (0) |
|---|---|---|---|---|---|---|---|---|
| gpt-6-sol@none | 14% | 30% | 7% | 14% | 0% | 0% | 0% | 0% |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| documents-documents-structure_ostrava_mutual_claims.md | documents | document | 74 | 6 | 100% |

## Documents And OCR

OCR runs once per scanned document, before and apart from the model runs.

| Document | Format | Words | Pages | OCR deployment | OCR pages | OCR s | OCR EUR |
|---|---|---|---|---|---|---|---|
| structure_ostrava_mutual_claims.md | md | 1925 | - | - | - | 0.0 | 0.0000 |
