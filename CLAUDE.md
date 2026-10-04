# Ontaix — project rules for Claude Code

Ontaix is a neutral control plane where a business describes itself as an ontology
("business as a product": owned, versioned domain products), sits above every data/AI/agent
platform, and governs agents. This repository is built by a team of Claude agents under one
orchestrator; the owner (Slim) reviews and approves at checkpoints.

## The one rule that outranks every other
`docs/design-system.md` and its source of truth `apps/studio/src/design/tokens.css` define the look of
the Ontaix Studio: colour meanings, fonts, shape, motion, focus and the AA contrast contract.
The Studio must follow it everywhere - canvas, teach bar, drawer, dialogs, toasts, menus, admin
portal - in light (the default) and dark. Read `docs/ui-contract.md` before touching anything
under `apps/studio`: it holds every behaviour, label, id, keyboard shortcut and ARIA rule the
Studio keeps. The screenshot suite under `tests/screenshots` compares every scene with its
stored baseline; a visible difference is a bug, not a design choice. Nobody "improves" the UI
without a decision recorded in `docs/decisions.md`. `reference/ontaix-studio-reference.html`
is the historical origin of the Studio's behaviour and markup (owner decision, 2026-10-04, ADR
0019); it is no longer the visual target and stays read-only, untouched.

## Repository layout
- `reference/` — the original demo file, the historical origin of the Studio. Read-only. Never edited, never deleted.
- `docs/` — design-system, ui-contract, provisioning, team-and-timeline, decisions (ADR log).
- `infra/terraform/azure` — Azure environment (France Central). `infra/scripts` — one-time bootstrap.
- `infra/helm` — the Ontaix chart (same chart on Azure and on plain Kubernetes).
- `apps/studio` — React 19 + TypeScript + Vite; the canvas renderer ported from the reference, styled by the design tokens.
- `apps/api` — Python 3.12 FastAPI modular monolith (ontology, proposals, identity, bindings, audit).
- `apps/gateway` — MCP gateway exposing the ontology to agents (read + propose, never write).
- `packages/connectors` — read-only connector SDK and connectors.

## Non-negotiables
- Every change to the ontology — concept, spec, relation, source, binding, attribute — is a
  proposal that a human approves or rejects. Agents propose; they never write directly.
- Authorisation is Ontaix-native (groups, roles in our database). OIDC is for authentication only.
  No dependency on Microsoft/Entra groups for what a user may do.
- Connectors are read-only by contract.
- Secrets exist only in `.env` files (ignored) and Azure Key Vault. Never in chat, code, commits,
  logs, tests, or documentation. Agents never ask the owner for a secret in a conversation.
- CI authenticates to Azure with GitHub OIDC federation. There is no client-secret path.
- Every agent works in its own folder through a pull request. QA and security agents review;
  they never author what they review. A blocked review is not overridden by a builder.
- Design tokens (`apps/studio/src/design/tokens.css`), OpenAPI spec, database schema and event
  catalogue are contracts; changing one goes through the architect agent and a note in
  `docs/decisions.md`.

## Conventions
- Azure names: `<type>-ontaix-<env>-<region>`; tags project/environment/owner/purpose/expires.
- Commits: conventional commits; PR description states which contract it implements and which
  screenshot baselines it touches.
- Tests run before a PR is opened: `pytest`, `vitest`, Playwright screenshot suite, `terraform validate`.
