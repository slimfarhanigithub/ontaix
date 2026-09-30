# Teach Bake-Off Report

Started 2026-09-29T21:34:42+00:00. Spent 0.5990 EUR of a 6.00 EUR budget (estimate before the run: 2.79 EUR).

## Screening

### Screening Ranking

| # | Configuration | Residency | Composite | Precision block | Recall block | Efficiency | Concept P | Recall (groundable) | Parent | Verb | Path | Invented | Missed | Mean level F1 | Degraded | Errors | Calls | Cost EUR | Mean s | p95 s | Output mode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | claude-sonnet-5@none | global | 0.452 | 0.395 | 0.180 | 1.000 | 30% | 32% | 37% | 61% | 24% | 87 | 80 | 4% | 51 | 0 | 54 | 0.5990 | 5.6 | 45.0 | json_schema |

### Screening By Suite

Concept F1 against groundable concepts / path accuracy / cost EUR, per suite (origin:mode).

| Configuration | dataset:speech |
|---|---|
| claude-sonnet-5@none | 31% / 24% / 0.599 |

### Screening Per Level

F1 of right-path concepts per tree level (1 = child of the company root), every level present. Expected counts in the header.

| Configuration | L1 (27) | L2 (55) | L3 (21) | L4 (9) | L5 (4) | L6 (1) | L7 (1) |
|---|---|---|---|---|---|---|---|
| claude-sonnet-5@none | 12% | 5% | 9% | 0% | 0% | 0% | 0% |

### Screening Speech Comprehension

Each recording is sent sentence by sentence as `speech` in one session; its final drafts are scored against the gold tree. Parent at depth: expected concepts drafted under an accepted parent at the expected level. Verb: matched concepts with an accepted verb. Relation: expected relations drafted with an accepted verb. Attribute: expected taught attributes drafted on the right concept with an accepted value.

| Case | Configuration | Repeat | Sentences | Parent at depth | Verb | Relation | Attribute | Depth reached / gold | Invented | Missed |
|---|---|---|---|---|---|---|---|---|---|---|
| en-speech-chain-bank | claude-sonnet-5@none | 0 | 1 | 0/6 | 2/4 | - | - | 3 / 5 | So the bank, Retail division, Retail division, Retail division, Um mortgages go through underwriting, Retail division, Underwriting produces an offer letter, Retail division, Retail division, Lending is split | Underwriting, Offer letter |
| en-speech-chain-seven-levels | claude-sonnet-5@none | 0 | 1 | 0/11 | 3/3 | - | - | 3 / 7 | So tallis digital, Delivery unit, Three practices cloud data, Delivery unit, Delivery unit, Uh the cloud practice runs migration, Delivery unit, Migrations uh consist of assessment planning, Delivery unit, Delivery unit, Cutover produces a runbook | Practices, Cloud, Data, Migrations, Assessment, Planning, Runbook, Rollback steps |
| en-speech-correction-lines | claude-sonnet-5@none | 0 | 1 | 0/5 | 0/0 | - | - | 0 / 2 | Okay so um the lyon plant, Line a line b, Okay so um the lyon plant, Line c no wait not line c line d, Okay so um the lyon plant, Uh the plant also has a paint shop | Lyon plant, Line A, Line B, Line D, Paint shop |
| en-speech-cross-domain-payroll | claude-sonnet-5@none | 0 | 1 | 0/1 | 0/0 | 0/2 | - | 0 / 3 | Employee submits a timesheet and um payroll, Pay the employee, Employee submits a timesheet and um payroll, Also the timesheet goes to the project manager for approval, Employee submits a timesheet and um payroll | Project manager |
| en-speech-customer-divisions-correction | claude-sonnet-5@none | 0 | 1 | 0/6 | 0/0 | - | - | 0 / 4 | Is a customer of halden engineering and it, Three divisions uh rail marine, Is a customer of halden engineering and it, E-commerce no sorry not e-commerce energy | Customer, Castellane S.A., Divisions, Rail, Marine, Energy |
| en-speech-fibre-order | claude-sonnet-5@none | 0 | 1 | 0/5 | 0/0 | - | - | 0 / 4 | So a fibre order um goes through feasibility then uh installation then activation and installation, Technician visit which uh books a slot | Feasibility, Installation, Activation, Technician visit, Slot |
| en-speech-grouping-count-corrected | claude-sonnet-5@none | 0 | 1 | 0/4 | 0/0 | - | - | 0 / 2 | - | Brands, Nordlys, Solbær, Fjellmat |
| en-speech-is-a-elliptical | claude-sonnet-5@none | 0 | 1 | 0/4 | 1/3 | - | - | 3 / 2 | Drone, Uh a helicopter is too, Aircraft | Helicopter |
| en-speech-it-relations | claude-sonnet-5@none | 0 | 1 | 0/0 | 0/0 | 0/2 | - | 0 / 0 | Warehouse management system um it, Warehouse management system um it, Warehouse management system um it, It gets order | - |
| en-speech-narration-org-structure | claude-sonnet-5@none | 0 | 7 | 6/9 | 6/7 | 0/2 | - | 3 / 3 | Organization also has sites and one of them, It, Posts too, And um the organization, Membership, Basically, Member | Site, Post |
| en-speech-narration-ssn-observations | claude-sonnet-5@none | 0 | 7 | 2/12 | 3/4 | 0/3 | - | 3 / 3 | Sensor observes an observable property and uh it, It's about a feature of interest, Feature of interest, Um observable properties are one kind of property | System, Sensor, Actuator, Sampler, Observable Property, Platform, Deployment, Procedure |
| en-speech-narration-valueflows-processes | claude-sonnet-5@none | 0 | 8 | 2/12 | 2/6 | 1/3 | - | 2 / 2 | Okay so um valueflows is basically built around, Process has inputs and outputs and uh those, It affects an economic resource, And a, And a, Is based, Processes are planned within a, Uh the plan includes commitment, Processes are planned within a, And agents so persons and organizations they, Receive the event | Process, Resource Specification, Plan, Agent, Person, Organization |
| en-speech-owner-financial-services | claude-sonnet-5@none | 0 | 6 | 0/8 | 0/3 | 0/5 | 0/2 | 3 / 4 | Sell, Financial, Service, Split, Managed | Financial services, Customers, Managed services, ADNOC, XRG |
| en-speech-question-aside | claude-sonnet-5@none | 0 | 1 | 0/3 | 0/1 | - | - | 2 / 2 | So returns um do we even, So returns um do we even, Ends with a credit note, So returns um do we even, Returns process i'm not sure actually yes we do the returns process start | Returns process, Credit note |
| en-speech-recording-correction | claude-sonnet-5@none | 0 | 4 | 0/4 | 2/2 | - | - | 3 / 3 | Okay so brenmoor insurance, Uh travel claim | Home claims, Fraud check |
| en-speech-recording-depot | claude-sonnet-5@none | 0 | 4 | 0/6 | 3/4 | - | - | 2 / 4 | So um harlow freight, So um harlow freight, And uh the depot, Split into chilled bays and frozen bay, And they each | Chilled bays, Frozen bays |
| en-speech-run-on-they | claude-sonnet-5@none | 0 | 1 | 0/4 | 1/1 | - | - | 2 / 3 | Right so we're a logistics company we've got warehouses and they're all bonded and um they each | Warehouses, Yard, Trailer slots |
| en-speech-these-policies | claude-sonnet-5@none | 0 | 1 | 0/4 | 0/0 | - | - | 0 / 2 | - | Insurance, Home, Motor, Travel |
| fr-speech-enregistrement-atelier | claude-sonnet-5@none | 0 | 3 | 0/4 | 0/0 | - | - | 0 / 3 | - | Usine, Atelier de découpe, Atelier de soudure, Robots |
| fr-speech-est-un-type-de | claude-sonnet-5@none | 0 | 1 | 0/4 | 0/0 | - | - | 0 / 2 | - | Aéronef, Drone, Hélicoptère, Carnet de route |
| fr-speech-inter-domaines-sla | claude-sonnet-5@none | 0 | 1 | 0/2 | 0/0 | 0/1 | - | 0 / 3 | Donc le ticket d'incident euh il est lié au contrat de, Et le sla du contrat fixe le délai de résolution | SLA, Délai de résolution |
| fr-speech-urgences-correction | claude-sonnet-5@none | 0 | 1 | 0/4 | 0/0 | - | - | 0 / 3 | - | Service des urgences, Accueil, Tri, Niveau de priorité |

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
