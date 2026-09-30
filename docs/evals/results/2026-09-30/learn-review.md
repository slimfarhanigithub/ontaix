# Teach Bake-Off Report

Started 2026-09-30T22:12:37+00:00. Spent 0.8785 EUR of a 34.60 EUR budget (estimate before the run: 1.17 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | gpt-6-sol@none | eu_data_zone | 0.961 | 0.975 | 0.911 | 1.000 | 97% | 97% | 98% | 98% | 93% | 5 | 5 | 85% | 0 | 0 | 54 | 0.5479 | 3.7 | 5.8 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | dataset:speech |
|---|---|
| gpt-6-sol@none | 97% / 93% / 0.548 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (31) | L2 (65) | L3 (43) | L4 (19) | L5 (5) | L6 (0) | L8 (0) |
|---|---|---|---|---|---|---|---|
| gpt-6-sol@none | 102% | 99% | 84% | 92% | 50% | 0% | 0% |

### Screening Speech Comprehension

Each recording is sent sentence by sentence as `speech` in one session; its final drafts are scored against the gold tree. Parent at depth: expected concepts drafted under an accepted parent at the expected level. Verb: matched concepts with an accepted verb. Relation: expected relations drafted with an accepted verb. Attribute: expected taught attributes drafted on the right concept with an accepted value.

| Case | Configuration | Repeat | Sentences | Parent at depth | Verb | Relation | Attribute | Depth reached / gold | Invented | Missed |
|---|---|---|---|---|---|---|---|---|---|---|
| en-speech-adr-owner-spoken | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 2 / 2 | - | - |
| en-speech-correction-i-meant | gpt-6-sol@none | 0 | 1 | 3/4 | 4/4 | - | - | 2 / 2 | - | - |
| en-speech-cross-domain-it | gpt-6-sol@none | 0 | 1 | 0/0 | 0/0 | 2/2 | - | 0 / 0 | - | - |
| en-speech-customer-also-supplier | gpt-6-sol@none | 0 | 1 | 5/5 | 5/5 | - | - | 3 / 3 | - | - |
| en-speech-false-starts | gpt-6-sol@none | 0 | 1 | 3/3 | 3/3 | - | - | 3 / 3 | - | - |
| en-speech-grouping-offerings | gpt-6-sol@none | 0 | 1 | 6/6 | 6/6 | - | - | 4 / 4 | - | - |
| en-speech-grouping-teams-corrected | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 3 / 2 | - | - |
| en-speech-hesitation-month-end | gpt-6-sol@none | 0 | 1 | 3/3 | 3/3 | - | - | 3 / 3 | - | - |
| en-speech-narration-dcat-catalogs | gpt-6-sol@none | 0 | 6 | 9/9 | 9/9 | 1/1 | - | 5 / 5 | - | - |
| en-speech-narration-goodrelations-offerings | gpt-6-sol@none | 0 | 7 | 13/13 | 13/13 | 1/1 | - | 3 / 3 | - | - |
| en-speech-narration-prov-o-starting-points | gpt-6-sol@none | 0 | 7 | 14/14 | 14/14 | 3/3 | - | 3 / 3 | - | - |
| en-speech-owner-adnoc-client | gpt-6-sol@none | 0 | 1 | 10/10 | 10/10 | - | - | 4 / 4 | - | - |
| en-speech-owner-financial-services | gpt-6-sol@none | 0 | 6 | 8/8 | 8/8 | 5/5 | 2/2 | 5 / 4 | - | - |
| en-speech-product-structure | gpt-6-sol@none | 0 | 1 | 7/7 | 7/7 | - | - | 5 / 5 | - | - |
| en-speech-recording-billing-drilldown | gpt-6-sol@none | 0 | 6 | 8/8 | 8/8 | 5/5 | 2/2 | 5 / 4 | - | - |
| en-speech-recording-under-each | gpt-6-sol@none | 0 | 6 | 10/11 | 10/10 | - | - | 3 / 3 | - | Plants |
| en-speech-retail-monologue | gpt-6-sol@none | 0 | 1 | 20/33 | 28/31 | - | - | 8 / 5 | Store, Members, Collection, Product range, Style | Formats, Tiers |
| fr-speech-chaine-banque | gpt-6-sol@none | 0 | 1 | 4/6 | 4/4 | - | - | 3 / 5 | - | Analyse de risque, Offre de prêt |
| fr-speech-fournisseur-division | gpt-6-sol@none | 0 | 1 | 6/6 | 6/6 | - | - | 3 / 3 | - | - |
| fr-speech-ils-elle | gpt-6-sol@none | 0 | 1 | 4/4 | 4/4 | - | - | 3 / 3 | - | - |
| fr-speech-offres-quatre-niveaux | gpt-6-sol@none | 0 | 1 | 5/5 | 5/5 | - | - | 4 / 4 | - | - |

### Screening Review Pass

The deeper model reviews each scored recording's drafts after the run's own model and returns corrections (rename, delete, move, add), applied to the drafted tree with every new label grounded in the recording; the recording is scored again. Cost and time are the review's own, apart from the run's model.

| Case | Configuration | Sentences | Parent at depth | Invented | Missed | Relations | Corrections (applied / refused) | Cost EUR | s |
|---|---|---|---|---|---|---|---|---|---|
| en-speech-adr-owner-spoken | gpt-6-sol@none | 1 | 4 to 4 of 4 | 0 to 0 | 0 to 0 | 0 to 0 of 0 | 0 (0 / 0) | 0.0029 | 3.5 |
| en-speech-correction-i-meant | gpt-6-sol@none | 1 | 3 to 3 of 4 | 0 to 0 | 0 to 0 | 0 to 0 of 0 | 0 (0 / 0) | 0.0202 | 10.9 |
| en-speech-cross-domain-it | gpt-6-sol@none | 1 | 0 to 0 of 0 | 0 to 3 | 0 to 0 | 2 to 2 of 2 | 3 (3 / 0) | 0.0290 | 10.6 |
| en-speech-customer-also-supplier | gpt-6-sol@none | 1 | 5 to 5 of 5 | 0 to 0 | 0 to 0 | 0 to 0 of 0 | 0 (0 / 0) | 0.0040 | 4.3 |
| en-speech-false-starts | gpt-6-sol@none | 1 | 3 to 3 of 3 | 0 to 0 | 0 to 0 | 0 to 0 of 0 | 0 (0 / 0) | 0.0028 | 3.4 |
| en-speech-grouping-offerings | gpt-6-sol@none | 1 | 6 to 6 of 6 | 0 to 1 | 0 to 0 | 0 to 0 of 0 | 1 (1 / 0) | 0.0281 | 13.1 |
| en-speech-grouping-teams-corrected | gpt-6-sol@none | 1 | 4 to 3 of 4 | 0 to 0 | 0 to 1 | 0 to 0 of 0 | 4 (1 / 3) | 0.0140 | 5.9 |
| en-speech-hesitation-month-end | gpt-6-sol@none | 1 | 3 to 3 of 3 | 0 to 0 | 0 to 0 | 0 to 0 of 0 | 0 (0 / 0) | 0.0029 | 5.1 |
| en-speech-narration-dcat-catalogs | gpt-6-sol@none | 6 | 9 to 9 of 9 | 0 to 0 | 0 to 0 | 1 to 1 of 1 | 0 (0 / 0) | 0.0057 | 3.9 |
| en-speech-narration-goodrelations-offerings | gpt-6-sol@none | 7 | 13 to 13 of 13 | 0 to 0 | 0 to 0 | 1 to 1 of 1 | 0 (0 / 0) | 0.0159 | 5.2 |
| en-speech-narration-prov-o-starting-points | gpt-6-sol@none | 7 | 14 to 14 of 14 | 0 to 0 | 0 to 0 | 3 to 3 of 3 | 0 (0 / 0) | 0.0075 | 5.8 |
| en-speech-owner-adnoc-client | gpt-6-sol@none | 1 | 10 to 10 of 10 | 0 to 0 | 0 to 0 | 0 to 0 of 0 | 0 (0 / 0) | 0.0051 | 4.8 |
| en-speech-owner-financial-services | gpt-6-sol@none | 6 | 8 to 8 of 8 | 0 to 0 | 0 to 0 | 5 to 5 of 5 | 0 (0 / 0) | 0.0143 | 8.0 |
| en-speech-product-structure | gpt-6-sol@none | 1 | 7 to 7 of 7 | 0 to 1 | 0 to 0 | 0 to 0 of 0 | 1 (1 / 0) | 0.0288 | 11.2 |
| en-speech-recording-billing-drilldown | gpt-6-sol@none | 6 | 8 to 8 of 8 | 0 to 0 | 0 to 0 | 5 to 5 of 5 | 0 (0 / 0) | 0.0371 | 16.8 |
| en-speech-recording-under-each | gpt-6-sol@none | 6 | 10 to 10 of 11 | 0 to 0 | 1 to 1 | 0 to 0 of 0 | 0 (0 / 0) | 0.0059 | 5.6 |
| en-speech-retail-monologue | gpt-6-sol@none | 1 | 20 to 12 of 33 | 5 to 1 | 2 to 2 | 0 to 0 of 0 | 10 (10 / 0) | 0.0637 | 14.1 |
| fr-speech-chaine-banque | gpt-6-sol@none | 1 | 4 to 6 of 6 | 0 to 0 | 2 to 0 | 0 to 0 of 0 | 2 (2 / 0) | 0.0103 | 7.2 |
| fr-speech-fournisseur-division | gpt-6-sol@none | 1 | 6 to 6 of 6 | 0 to 0 | 0 to 0 | 0 to 0 of 0 | 0 (0 / 0) | 0.0041 | 4.7 |
| fr-speech-ils-elle | gpt-6-sol@none | 1 | 4 to 4 of 4 | 0 to 0 | 0 to 0 | 0 to 0 of 0 | 0 (0 / 0) | 0.0031 | 6.2 |
| fr-speech-offres-quatre-niveaux | gpt-6-sol@none | 1 | 5 to 5 of 5 | 0 to 0 | 0 to 0 | 0 to 0 of 0 | 0 (0 / 0) | 0.0252 | 8.1 |

Over 21 recordings and 53 sentences: parent at depth 146 to 139 of 163, invented 5 to 6, missed 5 to 4; review cost 0.3306 EUR, 0.0062 EUR per reviewed sentence.

## Cases

| Case | Origin | Kind | Expected concepts | Relations | Grounding ceiling |
|---|---|---|---|---|---|
| en-speech-owner-financial-services | dataset | speech | 8 | 5 | 100% |
| en-speech-narration-goodrelations-offerings | dataset | speech | 13 | 1 | 100% |
| en-speech-narration-prov-o-starting-points | dataset | speech | 14 | 3 | 100% |
| en-speech-narration-dcat-catalogs | dataset | speech | 9 | 1 | 100% |
| en-speech-recording-billing-drilldown | dataset | speech | 8 | 5 | 100% |
| en-speech-recording-under-each | dataset | speech | 11 | 0 | 100% |
| en-speech-adr-owner-spoken | dataset | speech | 4 | 0 | 100% |
| en-speech-grouping-offerings | dataset | speech | 6 | 0 | 100% |
| en-speech-correction-i-meant | dataset | speech | 4 | 0 | 100% |
| en-speech-cross-domain-it | dataset | speech | 0 | 2 | 100% |
| en-speech-false-starts | dataset | speech | 3 | 0 | 100% |
| en-speech-grouping-teams-corrected | dataset | speech | 4 | 0 | 100% |
| en-speech-product-structure | dataset | speech | 7 | 0 | 100% |
| en-speech-hesitation-month-end | dataset | speech | 3 | 0 | 100% |
| en-speech-retail-monologue | dataset | speech | 33 | 0 | 100% |
| fr-speech-offres-quatre-niveaux | dataset | speech | 5 | 0 | 100% |
| fr-speech-chaine-banque | dataset | speech | 6 | 0 | 100% |
| fr-speech-ils-elle | dataset | speech | 4 | 0 | 100% |
| en-speech-owner-adnoc-client | dataset | speech | 10 | 0 | 100% |
| en-speech-customer-also-supplier | dataset | speech | 5 | 0 | 100% |
| fr-speech-fournisseur-division | dataset | speech | 6 | 0 | 100% |
