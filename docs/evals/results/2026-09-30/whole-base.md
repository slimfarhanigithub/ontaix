# Teach Bake-Off Report

Started 2026-09-30T21:00:19+00:00. Spent 1.0390 EUR of a 1.00 EUR budget (estimate before the run: 0.27 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@low | eu_data_zone | 0.971 | 0.985 | 0.927 | 1.000 | 99% | 92% | 100% | 97% | 100% | 1 | 6 | 93% | 1 | 0 | 4 | 0.0601 | 7.0 | 13.6 | json_schema |
| 2 | gpt-6-sol@none | eu_data_zone | 0.872 | 0.902 | 0.872 | 0.795 | 92% | 93% | 90% | 87% | 88% | 6 | 5 | 81% | 1 | 0 | 4 | 0.0695 | 9.6 | 22.0 | json_schema |
| 3 | claude-fable-5-1@low | global | 0.785 | 0.976 | 0.917 | 0.112 | 96% | 93% | 100% | 99% | 100% | 3 | 5 | 90% | 1 | 0 | 4 | 0.9094 | 44.2 | 74.4 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | documents:whole |
|---|---|
| gpt-6-sol@low | 95% / 100% / 0.060 |
| gpt-6-sol@none | 93% / 88% / 0.069 |
| claude-fable-5-1@low | 95% / 100% / 0.909 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (2) | L2 (12) | L3 (19) | L4 (37) | L5 (4) |
|---|---|---|---|---|---|
| gpt-6-sol@low | 80% | 96% | 97% | 94% | 100% |
| gpt-6-sol@none | 80% | 92% | 76% | 83% | 75% |
| claude-fable-5-1@low | 100% | 88% | 109% | 97% | 57% |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| documents-documents-structure_ostrava_mutual_claims.md | documents | document | 74 | 6 | 100% |

## Documents And OCR

OCR runs once per scanned document, before and apart from the model runs.

| Document | Format | Words | Pages | OCR deployment | OCR pages | OCR s | OCR EUR |
|---|---|---|---|---|---|---|---|
| structure_ostrava_mutual_claims.md | md | 1925 | - | - | - | 0.0 | 0.0000 |
