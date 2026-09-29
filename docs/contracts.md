# Contracts

The contracts under `contracts/` and the ADRs under `docs/adr/` are frozen when the owner approves them at checkpoint 1. Every builder agent implements against them; QA tests against them; nobody changes one without the architect and a row in `docs/decisions.md`.

## Index

| Contract | Governs | Consumers | Validation |
|---|---|---|---|
| `contracts/openapi.yaml` | Every HTTP endpoint of `apps/api`: resources, proposal-only mutations, pagination and filter conventions, Problem+JSON error codes, the scene snapshot, the WebSocket entry point | `apps/api` routers and Pydantic models, `apps/studio` generated client and mock API, `apps/gateway` client, QA contract tests | `npx --yes @redocly/cli lint contracts/openapi.yaml` |
| `contracts/schema.sql` | PostgreSQL 16 DDL: every table, enum, constraint, index, the append-only audit trigger, the outbox, the shared rate budgets (`rate_budget_window`), teach sessions, language model cost records and token usage, and the two reference-data inserts (domain templates, connector catalogue) | `apps/api` repositories and migrations, the Fuseki projector, QA fixtures | Load into a scratch PostgreSQL 16 (`uv run --no-project --with pgserver --with "psycopg[binary]"`, outside the repo), then insert the `origin_detail` and file-name bypass cases and expect every one to be refused, and run the conditional budget upserts of `rate_budget_window` and `llm_month_usage` past their limit and expect zero rows; `pglast` alone checks syntax only |
| `contracts/events.yaml` | AsyncAPI 3.0 event catalogue: NATS subjects, payload schemas, the WebSocket envelope and resume protocol | `apps/api` outbox writers and relay, the WebSocket hub, `apps/studio` event reducer, the Fuseki projector | `npx --yes @asyncapi/cli validate contracts/events.yaml` |
| `contracts/teach-extraction.schema.json` | JSON Schema 2020-12 of the only answer the teach extraction language model step may return: intents citing candidate handles or new labels, confidence, explanation, unresolved phrases (ADR 0008) | `apps/api` teach extraction adapter and validator, QA contract tests with recorded model answers | `uv run --no-project --with jsonschema python -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('contracts/teach-extraction.schema.json')))"` |
| `contracts/concept-expansion.schema.json` | JSON Schema 2020-12 of the only answer the concept expansion model step may return: suggestions under the handle `e0` at any depth, links inside the expansion, confidence and rationale (ADR 0009) | `apps/api` expansion adapter and validator, QA contract tests with recorded model answers | `uv run --no-project --with jsonschema python -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('contracts/concept-expansion.schema.json')))"` |
| `contracts/document-extraction.schema.json` | JSON Schema 2020-12 of the two answers a whole-document extraction job's model steps may return: outline nodes (pass 1) and section intents (pass 2), attached by handle, key or label path of any depth (ADR 0010) | `apps/api` extraction job runner and validator, QA contract tests with recorded model answers | `uv run --no-project --with jsonschema python -c "import json, jsonschema; jsonschema.Draft202012Validator.check_schema(json.load(open('contracts/document-extraction.schema.json')))"` |
| `contracts/design-tokens.json` | W3C design tokens with the verbatim values of the reference: CSS custom properties (dark and light), canvas theme, semantic colours, surfaces, typography, radii, layout, durations and easings, physics constants | `apps/studio` stylesheet and canvas theme generation, the Playwright screenshot suite | `python -c "import json; json.load(open('contracts/design-tokens.json'))"` |
| `docs/adr/0001` to `0012` | Module boundaries, proposal-only writes, native authorisation, persistence and projection, events, seeded randomness, Studio port strategy, teach extraction, concept expansion, whole-document extraction, import formats and OCR, ontology import | Every agent | Owner review at checkpoint 1; ADR 0008 by owner review of decision rows 75 to 79 and 83; ADR 0009 by rows 99 to 105; ADR 0010 by rows 105 to 109; ADR 0011 by rows 110 to 112; ADR 0012 by rows 113 to 115 |

Related, not contracts: `docs/requirements-addendum.md` is the product owner's extraction from the reference and the input these contracts were derived from; `docs/ui-contract.md` and `reference/ontaix-studio-reference.html` govern what the Studio looks like.

## How A Contract Changes

```mermaid
flowchart LR
  need[Builder or QA finds a gap] --> issue[Open an issue naming the contract and the gap]
  issue --> architect[Architect drafts the change in a PR touching contracts/ only]
  architect --> decision[Architect adds a row to docs/decisions.md]
  decision --> review[QA and security review the PR]
  review -->|blocked| architect
  review -->|approved| owner{Owner checkpoint or explicit approval}
  owner -->|approved| merge[Merge]
  merge --> regenerate[Consumers regenerate clients, models and fixtures]
  regenerate --> tests[Contract tests and screenshot suite run]
```

Rules:

- A builder never edits a file under `contracts/` in a feature PR. If the implementation needs a different shape, the builder opens an issue and works around it locally until the contract PR lands.
- Additive changes (a new optional field, a new endpoint, a new event) need the architect PR and the decisions row. Breaking changes (a removed or renamed field, a changed enum, a changed subject) also need the owner's explicit approval before merge.
- Every contract PR runs the seven validation commands above in CI.
- The OpenAPI version stays `1.0.0` during the fifteen days; breaking changes after the demo bump the major version and add `/api/v2`.
- Design token values are verbatim from the reference. A token value changes only when the reference changes first, so the screenshot suite stays the acceptance test.
- Schema changes ship as a migration next to the DDL; `contracts/schema.sql` always describes the current end state.
