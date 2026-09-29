# Team and timeline

The demo is built by 12 specialised agents under one orchestrator, from contracts frozen on day 1.
The owner is the only human: approves the contracts, reviews one PR bundle per checkpoint,
provides the Azure subscription (which also hosts the Azure AI Foundry model, reached without a key) and the design partner.

## Agents
| Role | Owns | Delivers |
|---|---|---|
| Orchestrator / tech lead | waves, merges, do-not rules | the plan, the merge queue |
| Product owner | `docs/` | requirements addendum extracted from the reference, demo script, arbitration |
| Architect | contracts | ADRs, OpenAPI, DB schema, event catalogue, design tokens |
| Backend: ontology & proposals | `apps/api/ontology`, `apps/api/proposals` | companies, domain products, concepts, relations, equivalences, versioning, approval contract, events |
| Backend: identity, groups, audit | `apps/api/identity`, `apps/api/audit` | OIDC login, native groups/roles, permissions, audit log, companies-may-interact switch |
| Data layer | `packages/connectors`, `apps/api/bindings` | connector SDK (read-only), Postgres/SQL Server/file connectors, discovery, bindings, coverage, lineage |
| Studio front end | `apps/studio` (canvas, shell) | verbatim renderer port, panel, drawer, teach bar, themes |
| Admin portal front end | `apps/studio/admin` | every admin page, dialogs, lists, wizard, appearance, cost management |
| NL & agents | `apps/api/nl`, `apps/gateway` | rule parser port, LLM extraction behind a neutral adapter, MCP gateway, agent registry + cost |
| QA | `tests/` | scene tests, contract tests, Playwright flows, screenshot regression vs reference |
| Security reviewer | reviews | secrets, read-only connectors, approval bypass, native authorisation — can block |
| Platform | `infra/` | Terraform, Helm, Compose, GitHub Actions, OpenTelemetry |

Rules: one folder per agent, every change through a PR; QA and security never author what they
review and can block; at most three builders on the same contract at once; builders never touch
secrets or the cloud — only platform does, and only from the environment.

## 15 working days
| Days | Wave | Checkpoint |
|---|---|---|
| 1 | Contracts: requirements addendum, ADRs, OpenAPI, schema, tokens, repo skeleton | **1** — owner approves the contracts |
| 2–4 | Foundations in parallel: ontology API, identity API, Compose + CI, canvas port against a mock API, QA scene tests | **2** — Studio shows Northwind + Aurora from a real API |
| 5–7 | Studio complete: admin portal, parser + LLM extraction, WebSocket live updates, two-user propose/approve, screenshot regression on | **3** — owner runs the whole demo story on the real product |
| 8–10 | Data and agents: connectors, bindings, coverage, lineage, MCP gateway, security review | **4** — an agent's proposal appears next to a human's |
| 11–13 | Ship: Terraform + Helm on Azure and on a plain cluster, demo script, rehearsal | — |
| 14–15 | Buffer; design partner schema loaded; dry run with the owner presenting | — |
