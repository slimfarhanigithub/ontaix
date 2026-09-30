# Teach Bake-Off Report

Started 2026-09-29T23:33:07+00:00. Spent 0.4459 EUR of a 3.00 EUR budget (estimate before the run: 1.02 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@none | eu_data_zone | 0.968 | 0.956 | 0.966 | 1.000 | 92% | 96% | 99% | 99% | 99% | 9 | 4 | 97% | 0 | 0 | 51 | 0.4459 | 2.1 | 3.9 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | dataset:speech |
|---|---|
| gpt-6-sol@none | 94% / 99% / 0.446 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (25) | L2 (52) | L3 (20) | L4 (7) | L5 (4) | L6 (1) | L7 (1) |
|---|---|---|---|---|---|---|---|
| gpt-6-sol@none | 94% | 92% | 93% | 100% | 100% | 100% | 100% |

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
| en-speech-it-relations | gpt-6-sol@none | 0 | 1 | 0/0 | 0/0 | 2/2 | - | 0 / 0 | Orders | - |
| en-speech-narration-org-structure | gpt-6-sol@none | 0 | 7 | 9/9 | 9/9 | 1/2 | - | 3 / 3 | Site, Membership | - |
| en-speech-narration-ssn-observations | gpt-6-sol@none | 0 | 7 | 10/12 | 11/11 | 1/3 | - | 3 / 3 | Features of interest, Platform | Feature Of Interest |
| en-speech-narration-valueflows-processes | gpt-6-sol@none | 0 | 8 | 12/12 | 12/12 | 3/3 | - | 3 / 2 | Economic events, Economic event | - |
| en-speech-question-aside | gpt-6-sol@none | 0 | 1 | 3/3 | 3/3 | - | - | 2 / 2 | - | - |
| en-speech-recording-correction | gpt-6-sol@none | 0 | 4 | 4/4 | 4/4 | - | - | 3 / 3 | Travel claims | - |
| en-speech-recording-depot | gpt-6-sol@none | 0 | 4 | 6/6 | 6/6 | - | - | 4 / 4 | - | - |
| en-speech-run-on-they | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 3 / 3 | Logistics company | - |
| en-speech-these-policies | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 2 / 2 | - | - |
| fr-speech-enregistrement-atelier | gpt-6-sol@none | 0 | 3 | 4/4 | 4/4 | - | - | 3 / 3 | - | - |
| fr-speech-est-un-type-de | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 2 / 2 | - | - |
| fr-speech-inter-domaines-sla | gpt-6-sol@none | 0 | 1 | 2/2 | 2/2 | 1/1 | - | 3 / 3 | - | - |
| fr-speech-urgences-correction | gpt-6-sol@none | 0 | 1 | 1/4 | 1/1 | - | - | 1 / 3 | - | Accueil, Tri, Niveau de priorité |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| en-speech-narration-valueflows-processes | dataset | speech | 12 | 3 | 100% |
| en-speech-narration-org-structure | dataset | speech | 9 | 2 | 100% |
| en-speech-narration-ssn-observations | dataset | speech | 12 | 3 | 100% |
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
| fr-speech-urgences-correction | dataset | speech | 4 | 0 | 100% |
| fr-speech-est-un-type-de | dataset | speech | 4 | 0 | 100% |
| fr-speech-inter-domaines-sla | dataset | speech | 2 | 1 | 100% |
| en-speech-customer-divisions-correction | dataset | speech | 6 | 0 | 100% |
| en-speech-recording-depot | dataset | speech | 6 | 0 | 100% |
| en-speech-recording-correction | dataset | speech | 4 | 0 | 100% |
| fr-speech-enregistrement-atelier | dataset | speech | 4 | 0 | 100% |
