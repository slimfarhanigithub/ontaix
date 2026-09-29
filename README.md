# Ontaix

A neutral control plane where a business describes itself as an ontology — owned, versioned
domain products — above every data, AI and agent platform, and governs the agents that use it.

- `reference/ontaix-studio-reference.html` — the approved Studio UI. Open it in a browser.
- `docs/ui-contract.md` — what "identical" means and how it is tested.
- `docs/provisioning.md` — Azure environment and the one-time bootstrap.
- `docs/team-and-timeline.md` — the agent team and the 15-day plan.
- `CLAUDE.md` — rules for the agents building this repository.

Start in VS Code with Claude Code from this folder; the orchestrator reads `CLAUDE.md` first.

## Repository Layout

```text
apps/
  api/          Python 3.12 FastAPI modular monolith (uv). Module boundaries for ontology,
                proposals, identity, bindings and audit are future work; see apps/api/README.md.
  gateway/      Python 3.12 FastAPI MCP gateway (uv): exposes the ontology to agents, read + propose, never write.
  studio/       React 19 + TypeScript + Vite; the Studio UI, ported verbatim from reference/.
packages/
  connectors/   Read-only connector SDK (Python, uv): discover and read only, enforced by test.
deploy/
  compose/      Local stack: postgres:16, api, gateway, studio.
infra/
  terraform/    Azure environment (France Central).
  scripts/      One-time bootstrap.
docs/           Contracts and decisions.
reference/      The Studio UI contract. Read-only.
.github/
  workflows/    ci.yml (apps and packages), infra.yml (Terraform).
```

```mermaid
flowchart LR
  agents[Agents] -->|MCP: read + propose| gateway[apps/gateway]
  studio[apps/studio] -->|HTTP| api[apps/api]
  gateway -->|HTTP| api
  api --> postgres[(PostgreSQL 16)]
  api -->|discover / read| connectors[packages/connectors]
  connectors -->|read-only| sources[(External sources)]
```

## Run Locally

Prerequisites: Node 22 or later with pnpm 9 (`corepack enable`), and uv 0.12 or later. uv downloads Python 3.12 on first use.

```bash
# Studio
pnpm install
pnpm --filter studio dev          # http://localhost:5173
pnpm --filter studio test
pnpm --filter studio build

# API (http://localhost:8000/healthz)
cd apps/api && uv sync && uv run uvicorn app.main:app --reload --port 8000

# Gateway (http://localhost:8100/healthz)
cd apps/gateway && uv sync && uv run uvicorn app.main:app --reload --port 8100

# Connectors
cd packages/connectors && uv sync && uv run pytest
```

### Studio Against the Real API

`pnpm dev:stack` (from the repository root, after `pnpm install`; it runs `uv sync` in `apps/api` when the virtualenv is missing) starts the whole stack without Docker:

1. an embedded PostgreSQL 16 from the api's `pgserver` dev dependency, whose data persists between runs in `%LOCALAPPDATA%\Ontaix\pgdata` on Windows (`~/.local/share/ontaix/pgdata` elsewhere; override with `ONTAIX_PGDATA`, or `ONTAIX_PGDATA=ephemeral` for a temporary database deleted on exit). `pnpm dev:stack -- --reset` deletes the data first for a clean start. Set `ONTAIX_DATABASE_URL` to use another server instead;
2. `python -m app.seed`: migrations, then an empty demo tenant: its settings and seeded users, the domain templates and the connector catalogue, and no company. The first company you add with "+ Company" becomes the home company. To load the Northwind Industries and Aurora Valves example instead, run `ONTAIX_SEED=fixture pnpm dev:stack`; an `ONTAIX_SEED` already set always wins, and it only matters for a new or reset database;
3. the API under uvicorn on http://127.0.0.1:8000 with `ONTAIX_ENVIRONMENT=dev` (selector event loop on Windows);
4. the Studio's Vite dev server on http://127.0.0.1:5173 with `VITE_ONTAIX_API_URL=/api/v1`, proxying `/api` to the API.

In this dev build the Studio identifies itself with `X-Ontaix-User`: `VITE_ONTAIX_DEV_USER`, else the seed's full-access demo user (`demo@northwind.com`: Administrator, Builder, Governor and Auditor), who can do everything in one tab; `?user=<email>` switches user per tab, for example the Builder (`sam.okafor@northwind.com`) or the Governor (`hugo.brandt@northwind.com`) to show separation of duties. Production builds send no such header. Ports come from `ONTAIX_API_PORT` and `ONTAIX_STUDIO_PORT`; Ctrl+C stops everything, the database included.

### Voice With Azure AI Speech

The teach bar microphone uses Azure AI Speech in France Central when the API has a Speech resource configured, and the browser's own recogniser otherwise (and whenever Azure Speech is unavailable or fails). To use it locally, run `az login` with an account that holds Cognitive Services Speech User on the Speech resource (Terraform grants it to the owner), then set in `apps/api/.env` the Terraform outputs `speech_resource_id` as `ONTAIX_SPEECH_RESOURCE_ID` and `speech_endpoint` as `ONTAIX_SPEECH_ENDPOINT` (`ONTAIX_SPEECH_REGION` stays `francecentral`). In `dev` the API mints the browser's token with your own `az login` session; in the cluster it uses the dedicated identity named by `ONTAIX_SPEECH_CLIENT_ID` (output `speech_identity_client_id`). The browser opens a WebSocket to the Speech service, so a Content Security Policy in front of the Studio must allow `wss://francecentral.stt.speech.microsoft.com` and `wss://<custom subdomain>.cognitiveservices.azure.com`.

`pnpm --filter studio test:e2e` boots the same stack with the fixture seed on ports 8788 and 5788, checks both companies and their concept counts, teaches and approves one concept, and writes `tests/e2e/output/studio-both-companies.png`.

Each Python package runs `uv run pytest` and `uv run ruff check`; the root `pnpm lint`, `pnpm test` and `pnpm build` cover every workspace package.

Full stack with Docker: copy `deploy/compose/.env.example` to `deploy/compose/.env`, then `docker compose -f deploy/compose/compose.yaml up --build`. Secrets live only in ignored `.env` files and Azure Key Vault.
