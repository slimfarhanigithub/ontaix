# Teach Bake-Off Report

Started 2026-09-29T22:41:51+00:00. Spent 3.1996 EUR of a 8.00 EUR budget (estimate before the run: 9.42 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | claude-fable-5-1@low | global | 0.975 | 0.967 | 0.972 | 1.000 | 95% | 98% | 99% | 97% | 99% | 6 | 2 | 96% | 0 | 0 | 55 | 3.1996 | 10.2 | 21.2 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | dataset:speech |
|---|---|
| claude-fable-5-1@low | 97% / 99% / 3.200 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (27) | L2 (55) | L3 (21) | L4 (9) | L5 (4) | L6 (1) | L7 (1) |
|---|---|---|---|---|---|---|---|
| claude-fable-5-1@low | 96% | 95% | 95% | 106% | 80% | 100% | 100% |

### Screening Speech Comprehension

Each recording is sent sentence by sentence as `speech` in one session; its final drafts are scored against the gold tree. Parent at depth: expected concepts drafted under an accepted parent at the expected level. Verb: matched concepts with an accepted verb. Relation: expected relations drafted with an accepted verb. Attribute: expected taught attributes drafted on the right concept with an accepted value.

| Case | Configuration | Repeat | Sentences | Parent at depth | Verb | Relation | Attribute | Depth reached / gold | Invented | Missed |
|---|---|---|---|---|---|---|---|---|---|---|
| en-speech-chain-bank | claude-fable-5-1@low | 0 | 1 | 6/6 | 6/6 | - | - | 5 / 5 | - | - |
| en-speech-chain-seven-levels | claude-fable-5-1@low | 0 | 1 | 11/11 | 11/11 | - | - | 7 / 7 | - | - |
| en-speech-correction-lines | claude-fable-5-1@low | 0 | 1 | 5/5 | 5/5 | - | - | 2 / 2 | - | - |
| en-speech-cross-domain-payroll | claude-fable-5-1@low | 0 | 1 | 1/1 | 1/1 | 2/2 | - | 3 / 3 | - | - |
| en-speech-customer-divisions-correction | claude-fable-5-1@low | 0 | 1 | 6/6 | 6/6 | - | - | 4 / 4 | - | - |
| en-speech-fibre-order | claude-fable-5-1@low | 0 | 1 | 5/5 | 5/5 | - | - | 4 / 4 | - | - |
| en-speech-grouping-count-corrected | claude-fable-5-1@low | 0 | 1 | 4/4 | 4/4 | - | - | 2 / 2 | - | - |
| en-speech-is-a-elliptical | claude-fable-5-1@low | 0 | 1 | 4/4 | 4/4 | - | - | 2 / 2 | - | - |
| en-speech-it-relations | claude-fable-5-1@low | 0 | 1 | 0/0 | 0/0 | 2/2 | - | 0 / 0 | - | - |
| en-speech-narration-org-structure | claude-fable-5-1@low | 0 | 7 | 9/9 | 9/9 | 1/2 | - | 3 / 3 | Membership | - |
| en-speech-narration-ssn-observations | claude-fable-5-1@low | 0 | 7 | 10/12 | 11/11 | 1/3 | - | 3 / 3 | Features of interest, Platform | Feature Of Interest |
| en-speech-narration-valueflows-processes | claude-fable-5-1@low | 0 | 8 | 12/12 | 12/12 | 3/3 | - | 3 / 2 | Economic events, Economic event | - |
| en-speech-owner-financial-services | claude-fable-5-1@low | 0 | 6 | 8/8 | 8/8 | 5/5 | 2/2 | 5 / 4 | - | - |
| en-speech-question-aside | claude-fable-5-1@low | 0 | 1 | 3/3 | 3/3 | - | - | 2 / 2 | - | - |
| en-speech-recording-correction | claude-fable-5-1@low | 0 | 4 | 4/4 | 4/4 | - | - | 3 / 3 | Travel claims | - |
| en-speech-recording-depot | claude-fable-5-1@low | 0 | 4 | 6/6 | 6/6 | - | - | 4 / 4 | - | - |
| en-speech-run-on-they | claude-fable-5-1@low | 0 | 1 | 4/4 | 4/4 | - | - | 3 / 3 | - | - |
| en-speech-these-policies | claude-fable-5-1@low | 0 | 1 | 4/4 | 1/4 | - | - | 2 / 2 | - | - |
| fr-speech-enregistrement-atelier | claude-fable-5-1@low | 0 | 3 | 4/4 | 4/4 | - | - | 3 / 3 | - | - |
| fr-speech-est-un-type-de | claude-fable-5-1@low | 0 | 1 | 4/4 | 4/4 | - | - | 2 / 2 | - | - |
| fr-speech-inter-domaines-sla | claude-fable-5-1@low | 0 | 1 | 2/2 | 2/2 | 1/1 | - | 3 / 3 | - | - |
| fr-speech-urgences-correction | claude-fable-5-1@low | 0 | 1 | 3/4 | 3/3 | - | - | 3 / 3 | - | Accueil |

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| en-speech-owner-financial-services | dataset | speech | 8 | 5 | 100% |
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
