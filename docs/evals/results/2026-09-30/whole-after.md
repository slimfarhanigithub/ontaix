# Teach Bake-Off Report

Started 2026-09-30T21:16:55+00:00. Spent 1.0673 EUR of a 1.20 EUR budget (estimate before the run: 0.27 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@low | eu_data_zone | 0.961 | 0.975 | 0.919 | 0.990 | 96% | 92% | 100% | 99% | 100% | 3 | 6 | 92% | 1 | 0 | 4 | 0.0647 | 7.5 | 13.8 | json_schema |
| 2 | gpt-6-sol@none | eu_data_zone | 0.922 | 0.915 | 0.906 | 0.963 | 87% | 96% | 100% | 93% | 100% | 11 | 3 | 85% | 0 | 0 | 4 | 0.0633 | 8.1 | 20.1 | json_schema |
| 3 | claude-fable-5-1@low | global | 0.772 | 0.935 | 0.934 | 0.120 | 87% | 99% | 100% | 100% | 100% | 11 | 1 | 88% | 0 | 0 | 4 | 0.9393 | 43.7 | 79.1 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | documents:whole |
|---|---|
| gpt-6-sol@low | 94% / 100% / 0.065 |
| gpt-6-sol@none | 91% / 100% / 0.063 |
| claude-fable-5-1@low | 92% / 100% / 0.939 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (2) | L2 (12) | L3 (19) | L4 (37) | L5 (4) |
|---|---|---|---|---|---|
| gpt-6-sol@low | 80% | 88% | 97% | 94% | 100% |
| gpt-6-sol@none | 80% | 81% | 97% | 95% | 73% |
| claude-fable-5-1@low | 100% | 92% | 100% | 96% | 53% |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| documents-documents-structure_ostrava_mutual_claims.md | documents | document | 74 | 6 | 100% |

## Documents And OCR

OCR runs once per scanned document, before and apart from the model runs.

| Document | Format | Words | Pages | OCR deployment | OCR pages | OCR s | OCR EUR |
|---|---|---|---|---|---|---|---|
| structure_ostrava_mutual_claims.md | md | 1925 | - | - | - | 0.0 | 0.0000 |
