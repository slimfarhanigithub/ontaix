# Teach Bake-Off Report

Started 2026-09-29T23:40:06+00:00. Spent 0.2710 EUR of a 1.00 EUR budget (estimate before the run: 0.30 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@none | eu_data_zone | 0.997 | 1.000 | 0.991 | 1.000 | 100% | 98% | 100% | 100% | 100% | 0 | 1 | 100% | 0 | 0 | 33 | 0.2710 | 1.9 | 3.1 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | dataset:typed |
|---|---|
| gpt-6-sol@none | 99% / 100% / 0.271 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (14) | L2 (30) | L3 (12) | L4 (5) | L5 (2) | L6 (1) |
|---|---|---|---|---|---|---|
| gpt-6-sol@none | 100% | 98% | 100% | 100% | 100% | 100% |

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
