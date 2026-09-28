# ADR 0005: Events And Live Updates

Status: Proposed. Pending owner approval at checkpoint 1.

## Context

The reference redraws every frame from shared arrays, so one browser always sees its own changes. With two users, or a human and an agent, a second user's approval must show the green rim and the version bump without a reload. Decision 5 places NATS in the cluster. The Fuseki projector (ADR 0004) and any future consumer need the same stream.

## Decision

Every state change that other clients or services must see is published as an event described in `contracts/events.yaml` (AsyncAPI 3.0). Events are written with the outbox pattern and flow to NATS internally and to the Studio over WebSocket.

```mermaid
sequenceDiagram
  participant S as Studio A
  participant API as API
  participant PG as PostgreSQL
  participant R as Outbox relay
  participant N as NATS
  participant WS as WebSocket hub
  participant B as Studio B
  S->>API: POST /proposals/{id}/approve
  API->>PG: BEGIN · apply · audit · INSERT outbox · COMMIT
  API-->>S: 200 proposal
  R->>PG: SELECT unpublished outbox rows
  R->>N: publish ontaix.{tenant}.proposal.approved
  R->>PG: mark published
  N->>WS: deliver
  WS-->>B: envelope over /api/v1/ws
  WS-->>S: same envelope (idempotent by id)
```

Rules:

- Outbox: the request handler inserts one `outbox` row per event inside the business transaction. A relay polls unpublished rows in id order, publishes them to NATS JetStream and marks them published. An event never exists without its state change and a state change never exists without its event.
- Subjects: `ontaix.{tenantId}.{aggregate}.{action}`, for example `ontaix.7f1c….proposal.approved`, `ontaix.7f1c….concept.born`. Consumers subscribe with wildcards (`ontaix.*.proposal.>`).
- WebSocket: one endpoint, `GET /api/v1/ws`, authenticated with a one-time ticket. The client first calls `POST /api/v1/ws/ticket` with its bearer token and receives an opaque ticket bound to its identity, valid for 30 seconds and for one connection; it opens the socket with `?ticket=`. A bearer token never appears in a URL, so it never lands in access logs, proxies or browser history. The server sends events in one envelope shape: `{ id, type, occurredAt, tenantId, companyIds, sequence, actor, bulk, payload }`. `sequence` is the tenant-wide outbox id, so a subscriber sees gaps where events were filtered out for it; a client reconnects with `?since=<sequence>` and receives what it missed, or a `snapshot.required` message when the gap is too old, in which case it reloads `GET /api/v1/scene`.
- Visibility: every channel in `contracts/events.yaml` declares `x-ontaix-visibility`, the permission a subscriber must hold to receive it: `model.read` for ontology events, `audit.read` for `audit.appended`, `group.manage` for `group.changed`, `agent.manage` for `agent.changed`.
- Audience: every event carries `companyIds`, the companies whose labels, names or artefact state its payload carries; bare ids do not count, and an empty list means tenant-wide. A subscriber receives an event only if it holds the visibility permission in a scope that contains every listed company; with an empty list, the permission at any scope suffices. A cross-company proposal or relation, and its audit entry, therefore reach only readers of both companies. Each channel declares `x-ontaix-audience`: `companies` (filled from the payload's artefacts) or `tenant` (always empty; the payload carries counts, ids or tenant settings only).
- Partitioning: an event on a `companies` channel never mixes artefacts with different company sets. The writer partitions them and emits one event per company set: `source.refreshed` is emitted per company, and a proposal cascaded by a rejection whose companies are not all in the rejected proposal's set gets its own `proposal.rejected`. A one-company reader never loses an event about something it can read, and never receives a label it cannot read.
- Transport of the audience: the outbox row stores `visibility` and `company_ids` (`uuid[]`, default empty; there is no single `company_id`). A trigger checks on insert that every listed company belongs to the row's tenant, which replaces the composite foreign key an array cannot carry. The relay copies both into the NATS headers `Ontaix-Visibility` and `Ontaix-Company-Ids`, and the hub filters on them without re-deriving them.
- Audit: `audit_entry.company_ids` follows the same rule, so `GET /audit` and `audit.appended` show a company-scoped Auditor or Governor only entries about companies it may read. Entries with no proposal list their companies too: a company addition lists the new company, a role assignment lists the company of its scope.
- CORS: the API sends CORS headers for an explicit origin allow-list from configuration, never a wildcard. Authentication is bearer tokens only, no cookies, so there is no CSRF surface.
- Ordering: events of one tenant are delivered in outbox id order. Clients ignore an event whose `sequence` is not greater than the last one applied.
- Payloads carry the full new state of the affected artefact (the proposal with its `ready` and `waitFor`, the concept with `pending`, the domain product with its `revision`), not a diff, so a client can apply an event without a fetch. Bulk operations (`approve-all`, `finalise-all`, the companies-may-interact disable) set `bulk: true` on every event they emit so that the Studio softens the flash and skips the toast, as the reference does.
- Immediate changes (settings, appearance, groups, roles, source enable/disable, agent access) also emit events, so a second admin window updates live.

## Consequences

- The Studio keeps its "redraw from arrays" model: the arrays are filled by `GET /scene` and kept current by the WebSocket.
- The Fuseki projector, the audit exporter and any future integration consume the same NATS stream.
- The relay is the only component that publishes, so a NATS outage delays events but never loses them.
