# ADR 0018: Platform Access to an Organization

Status: Accepted. The requirement is an owner decision (Slim, 2026-10-04); the design is approved under owner delegation (decision row 169). It supersedes ADR 0017 section 3 where that section makes the read-only support session the super admin's only way into an organization.

## Context

The owner asked, verbatim: "I want the super admin to be able to login every tenant and do everything on it".

ADR 0017 gives the super admin a platform role outside every organization and, inside one, only an audited read-only support session with `model.read`, `directory.read` and `audit.read`. Every write inside an organization needs a directory user of that organization: proposals, approvals, document imports, rate budgets and teach sessions all name a user through a composite foreign key or a check on the actor kind, and the separation of approvers compares user ids. The isolation of ADR 0017 section 7 (row-level security under the application role) must hold for the super admin exactly as for a member, and ontology changes must stay proposals.

## Decision

### 1. Entering and Leaving

From the platform portal the super admin picks an organization and chooses `Enter`. `POST /admin/organizations/{organizationId}/enter` replaces the session with a new token whose row names the organization in `auth_session.acting_tenant_id` and the end of the access in `acting_until`, 60 minutes from the entry and never past the session's absolute expiry, as a support session has; `POST /admin/exit` replaces it with a token naming none. Both require a live `super_admin` session and the CSRF token, as every unsafe `/admin` call does; a request whose session another request ended first answers `409 session_changed`. A session holds a support organization or an acting organization, never both: entering ends an open support session, and opening a support session ends the entry, each audited. The access lasts until its hour passes, until the super admin leaves or signs out, or until the session ends by its idle or absolute timeout; the super admin enters again to continue. `resolve_session()` returns the acting organization only while the hour runs, the organization is enabled and the account still holds `super_admin`, so a revoked role ends the access at the next request. Disabling the organization ends every session acting inside it, as it ends its members' sessions. The cookie keeps its shape; nothing is stored in the browser.

```mermaid
sequenceDiagram
  participant S as Studio (platform portal)
  participant A as API /admin
  participant P as PostgreSQL (ontaix_platform)
  participant O as PostgreSQL (ontaix_app, RLS)
  S->>A: POST /admin/organizations/{id}/enter + CSRF
  A->>P: directory user (issuer platform) of the organization, created once
  A->>P: end session, insert auth_session(acting_tenant_id)
  A->>P: platform_audit_entry organization_entered, audit_entry kind platform
  A-->>S: Session{acting} + Set-Cookie
  S->>A: POST /concepts (cookie)
  A->>O: resolve_session → acting_tenant_id; set_config('ontaix.tenant_id', acting)
  A->>O: proposal by the directory user, audit_entry actor user + actor_account_id
```

### 2. Acting Inside

An organization request of an acting session resolves to a `Caller` of kind `user`: the super admin's directory user of that organization, with issuer `platform` and subject `<account id>:<tenant id>` (subjects are unique across issuers), created at the first entry with his account's name and email. It belongs to no group; its grants are Administrator, Builder, Governor and Auditor at tenant scope, held by the access alone, so every tenant permission applies: teach, propose, approve and reject, edit, delete, companies, domains, settings, export, cost, the audit log. Owner is company-scoped and adds nothing beyond Builder and Governor at tenant scope. The request runs on the application role with `ontaix.tenant_id` set to the organization, exactly as a member's request, so row-level security confines it to that organization; `ontaix_platform` is never used for organization data. The separation of approvers compares that user's id, so the super admin cannot give both approvals of one proposal. Ontology changes stay proposals, which he may approve. The API serves no directory endpoints today, so the directory user is reachable only through the rows it writes; the platform portal's user count counts accounts, so it does not count him. When directory endpoints land, a user of issuer `platform` is neither deletable nor renamable by an organization's Administrator: a deletion would cascade through the proposals, approvals and imports it wrote and erase the super admin's trace, and its name and email belong to his platform account.

### 3. Accountability

Entering writes `organization_entered`, and every way the access ends writes `organization_exited`, to the platform log and, as kind `platform`, to the organization's own log, where its Administrators, Governors and Auditors read them, with a sentence saying why: an exit, another organization entered, a support session opened, sign-out, a password change or reset, the account or the organization disabled, the session limit, the hour of access or the session expired, or the super admin role revoked. The row records that its exit is audited (`auth_session.acting_exited_at`), so each end is written exactly once whichever path sees it first: the request that ends it writes the entry with that request's actor, and the sign-in upkeep sweep, every minute, writes the ends no request saw (expiry, a revoked role, a disabled account) with the system as actor. Every entry an action inside writes to the organization's log has actor kind `user` and carries the super admin's platform account in `audit_entry.actor_account_id`, the marker of platform access; the contract exposes it as `actor.platformAccountId` on `AuditEntry` and on every event's `actor`. The constraint `audit_entry_platform_actor` allows the account on `user` entries and still requires it on `platform` entries and forbids it on `agent` and `system` ones.

### 4. Studio

The Organizations page gains an `Enter` row action before `Open`; it asks `Enter <organization>?` with the body `You act inside <organization> with every role, as platform super admin. Everything you do there is recorded in its audit log.` and the button `Enter`. Inside, the Studio shows the organization as a member with those roles would see it, with the banner `#platformAccess` fixed at the top centre above the Studio and the admin portal: `Acting in <organization> as platform super admin · <n> min left` with the `Exit` button, built from the reference's `.btn`, `--panel`, `--accent` and `--line`; the minutes count down, and when the hour ends the Studio reads the session again and returns to the portal. Every change of session or organization bumps a generation counter in the store: the previous organization's scene and directory are dropped at once, and an answer of theirs still in flight lands nowhere. The organization's audit log page appends ` · platform super admin` to the text of every entry whose actor carries `platformAccountId`. The Studio-only baselines of the Organizations page change for the new action (decision row 169).

### 5. Threat Model

A stolen super admin session can now act inside every organization, where before it could only read inside one at a time after giving a reason. It is bounded by the hour of access (`acting_until`, 60 minutes per entry, re-entered explicitly and audited each time), the session's idle timeout (30 minutes) and absolute timeout (12 hours), the `HttpOnly`, `Secure`, host-only cookie, the CSRF token and `Origin` check on every write including the entry, the token rotation at every entry and exit (a second request on a replaced session answers `409 session_changed`), the `super_admin` role checked on every request through `resolve_session()`, the audit entries in the platform log and in the organization's log that name the account and the client IP for the entry and for every end, written once whichever way the access ends, the banner that shows the access and the minutes left on every screen, and the fact that entering an organization never changes accounts, roles, passwords or the platform role, so a stolen session cannot make itself permanent. An ended session loses the access at once; disabling an account or an organization, resetting a password and revoking the role end the access, each audited.

## Consequences

- The super admin can do everything a tenant Administrator, Builder, Governor and Auditor can, in every organization, with every action attributed to him twice: as the organization's directory user and by his platform account.
- `contracts/schema.sql`, `contracts/openapi.yaml` and `contracts/events.yaml` change additively: `auth_session.acting_tenant_id`, `acting_until` and `acting_exited_at`, the `access_changed` session end reason, the two platform log actions, `resolve_session()` returning the acting organization, the relaxed audit actor check, `Session.acting`, `Actor.platformAccountId` and the two endpoints. Migration `0010_platform_access` applies them; migration `0008` drops and creates `resolve_session()` instead of replacing it, because its result row differs between the two revisions.
- The read-only support session stays for looking without the ability to change anything.
- The dev identity header, the seed and the admin CLI are unchanged; no setting is added.
