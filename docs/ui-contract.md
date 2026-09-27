# Ontaix Studio — UI contract

The file `reference/ontaix-studio-reference.html` is the contract. It was built and approved
screen by screen with the owner; every rule below was a decision taken while building it.

## Acceptance
- Playwright screenshot suite: each scene below is rendered from the reference file and from the
  Studio at 1440×900 and 1920×1080, dark and light, and compared with a 0.1 % pixel tolerance.
- Scenes: empty canvas; first company seeded; story played to the end; pending proposals visible;
  approve / reject; domain focus; cell focus; lineage drawer; Arrange in each mode (full, domain,
  cell, lineage); Coverage view; every admin page; data-source wizard steps 1–3; relationship
  dialog; type-"disable" confirmation; two companies with equivalences; legend shown and hidden.
- The cell-division animation is compared frame-by-frame at 6 sampled frames.

## Do-not rules (each one was explicitly rejected by the owner)
- No glows, halos, particles, light bridges, shadow ghosts, dotted rims, or orbit lines. Cells are
  plain matte spheres with nothing around or inside them; a green rim after approval, a red fade
  after rejection, nothing else.
- No gamification: no levels, XP, trophies, bonuses, unlocks.
- No explosion or flash on division. A cell divides through a metaball neck with throb, mutual
  push, cleavage furrow and recoil; the child visibly comes out of the parent.
- No stripe across a newborn cell, no line inside a cell during colour changes.
- No `prompt()` / `alert()` / `confirm()`. Dialogs only, closed with an × button — no Cancel buttons.
- No verb chips in the relationship dialog; a text box with propose-change, suggest and
  reverse-direction icons.
- Enable/Disable toggles are fixed-width and aligned; never "Show/Hide" wording in the admin portal.
- Domain colour is identical for every cell in the domain and the same across companies; no
  brighter nuance inside a cluster.
- Company hull is fully filled, not a ring.
- No dependency on Microsoft for groups: native Ontaix groups.

## Behaviours that must be reproduced exactly
- Proposal contract: propose → pending (drawn lighter, "awaiting approval") → approve (green rim,
  domain version +1) / reject (red fade, cascade to descendants); two-approver option; audit log;
  Finalise all; Skip animation.
- Cells are born only by division from a parent; lineage (parent, birth link, born-at) is persisted.
- Teach: rule-based parser first (subject → action → object, "is a", "In <domain>, …", lists,
  passives); anything unresolved becomes a proposed new cell, never a silent creation.
- Suggest action: subject's own actions first, then DOES by subject, then DONE_TO by object.
- Focus: hover shows the neighbourhood; click is sticky focus; domain click focuses the domain
  using the nearest-cell rule; Arrange acts on the highlighted set only and stages it in a clear
  area to the right of everything else, then fits.
- Coverage view fades unbound cells; sources are brass rounded squares anchored outside the
  domain ring; bindings carry record counts and freshness; discovered attributes are proposed.
- Admin portal pages, in this order: Overview, Tenant settings, Appearance, Data sources,
  Connectors, Entities, Relationships, Bindings, Companies, Domain products, Groups, Users,
  Roles, Audit log, Cost management. Lists are searchable, filterable, sortable, paginated
  (thousands of agents expected). Adding a company from the portal keeps the portal open.
- "Companies may interact" switch: disabling it when links exist requires typing `disable`
  and removes every cross-company link.
- Theme switch (dark/light) in the admin header and Appearance; colour pickers per domain.
- Keyboard: P panel, D domains card, L legend, G admin.
- Everything persists (state survives reload and full-screen).

## Porting rule
The canvas renderer (cells, division, hulls, links, labels, arrange, focus, lineage) is ported
from the reference **verbatim** into TypeScript modules. Refactoring for structure is allowed;
changing a constant, an easing, a colour or a threshold is not.
