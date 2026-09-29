# Ontaix Studio — UI contract

The file `reference/ontaix-studio-reference.html` is the contract. It was built and approved
screen by screen with the owner; every rule below was a decision taken while building it.

## Acceptance
- Playwright screenshot suite: each scene below is rendered from the reference file and from the
  Studio at 1440×900 and 1920×1080, dark and light, and compared with a 0.1 % pixel tolerance.
- The scripted story is not part of the product (decision row 62). The reference file still contains it and is never edited; the harness injects one stylesheet into both the reference page and the Studio page that hides the story-only elements listed below, so the Studio is compared against the reference without them.
- Hidden in both pages by the injected stylesheet, with `display: none` so the surrounding layout closes up as it does in a Studio that never renders them: `#sceneNum` (the `Scene n of 14` counter, statically `Scene 0 of 15`) and `#sceneName` (the scene name) inside the header's `.scene` block, whose admin button `#adminOpen` stays visible; `#next` (the Next button with `#nextLabel`, for example `Next · Supply chain`); `#finalise` (the Finalise all tool button).
- `.hint` is compared pixel by pixel. Only its two story fragments go: a script the harness injects into both pages removes the first `kbd` (`Space`) and the whole text node after it (` next`, a space, a no-break space, a space), removes the last `kbd` (`R`) and the whole text node after it (` restart`), and replaces the text node after `<kbd>F</kbd>` with exactly ` full screen` (the reference's ` full screen `, a space, a no-break space and a space, carry the separator before `R`, and a no-break space does not collapse). The Studio renders the hint markup already in that form, so the script changes nothing there. Before the screenshot the harness asserts that `.hint` `textContent` is equal in both pages.
- Teach-bar placeholder: when `#say` is empty the Studio shows the reference's own non-story placeholder `Teach <company name>…` for the company being taught, with any number of companies, and `Live teaching is disabled in the admin portal` when live teaching is off, as the reference does. The reference shows `Teach <company name>…` only when it has two or more companies; with one company it shows the story text `Teach the model something, or press Next to follow the story`. The harness therefore compares the placeholder in every scene with two or more companies or with live teaching off, and makes `#say::placeholder` transparent in both pages only in scenes with one company and live teaching on.
- `.caption` is also hidden while the reference still shows the story's opening caption (kicker `Say what your business does`, text about Northwind Industries), which it does until the first teach, import or decision replaces it; after that the caption holds teach, import or approval text and is compared. The Studio renders `.caption` with an empty kicker and empty text until its first teach, import or decision, so no opening copy ships.
- The harness never plays a scene. It drives the reference through the paths the product keeps: sentences go through the reference's import path (`teach(sentence, true)`), which skips story interception; companies through the add-company dialog; sources and bindings through the data-source wizard; relations and cross-company equivalences through the relationship dialog (drop across companies, action `equivalent to`); decisions through the changes panel, Approve all and Reject all. It drives the Studio through the same user actions against the API, starting from the dev and test fixture's home company, Northwind Industries. Both reach the same state with the same seed and clock.
- Scenes: empty canvas (home company root only); a company added with its starter vocabulary pending; full fixture model - Northwind Industries taught through text and document import, Aurora Valves added with its starter vocabulary, sources bound through the wizard, equivalences proposed through the relationship dialog, everything approved with Approve all; pending proposals visible; approve / reject; domain focus; cell focus; lineage drawer; Arrange in each mode (full, domain, cell, lineage); Coverage view; every admin page; data-source wizard steps 1–3; relationship dialog; type-"disable" confirmation; two companies with equivalences; legend shown and hidden.
- The cell-division animation is compared frame-by-frame at 6 sampled frames.
- Waiting for teach extraction (up to 15 seconds for a typed or document sentence, 45 seconds for a speech transcript, decision row 91) adds no UI: the Studio shows exactly what the reference shows while a sentence is being taught, with no spinner, progress text or new status pill.
- Refusal toasts differ from the reference on purpose (decision row 86). When the API refuses an action, the toast keeps the bold lead `Refused` and its body text is the Problem's `detail` (its `title` when `detail` is absent), rendered as text, for example `Refused Only a Governor or Owner can approve`. The reference has no server, so it has no refusal reasons. Only that body text differs; the toast's position, style, animation and 3-second life are the reference's. Screenshot scenes include no refusal toast.
- Deleting a concept differs from the reference on purpose (decision row 98). The cell drawer has a third action, `Delete` (`#drDelete`), after `Grow a concept from it` and `Lineage`, in the same `.drawer .actions button` style; it shows only for approved, live, non-root concepts and opens the same confirmation as Admin portal → Entities → Delete. That confirmation, from both entry points, reads `Delete <label>?` with the body `Its <n> descendants (<names>) and <m> relations go with it. This proposes a change for approval.` (singular forms for one; at most 6 names, then `and <k> more`; `Its <m> relations go with it. This proposes a change for approval.` when nothing descends from it), names rendered as text. Screenshot scenes: the injected stylesheet hides `#drDelete` in both pages with `display: none` (the reference has no such element), so every drawer and lineage scene compares the rest of the drawer against the reference at the usual tolerance; the Entities page scene is unaffected, and no scene shows the delete confirmation.

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
  Approve all / Reject all; Skip animation.
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
- Keyboard: P panel, D domains card, L legend, G admin, A arrange, I import, C coverage, S skip animation, F full screen, Escape; no Space, ArrowRight or R (story shortcuts, removed by decision row 62).
- Content enters as speech (teach bar microphone, transcribed to text), text (teach bar) or documents (import, extracted by the API); each becomes proposals.
- Everything persists (state survives reload and full-screen).

## Porting rule
The canvas renderer (cells, division, hulls, links, labels, arrange, focus, lineage) is ported
from the reference **verbatim** into TypeScript modules. Refactoring for structure is allowed;
changing a constant, an easing, a colour or a threshold is not.
