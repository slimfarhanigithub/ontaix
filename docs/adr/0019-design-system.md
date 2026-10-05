# ADR 0019: The Design System Replaces the Reference as the Visual Source of Truth

Status: Accepted. The redesign is an owner decision, final (Slim, 2026-10-04): "I want you to follow this file docs/DESIGN-SYSTEM to redesign the app". The three answers below are the owner's; everything else here is approved under owner delegation (decision row 167).

## Context

Since decision row 1 the Studio had to be pixel-identical to `reference/ontaix-studio-reference.html`: a teal accent on a near-black navy canvas, Sora from Google Fonts, translucent blurred panels, and a screenshot suite that rendered the reference and the Studio side by side and compared them. Every owner addition since (the compact teach bar, the canvas docks, the drawer menu, export, editing) was hidden from that comparison so the reference could stay the acceptance test.

The owner wrote a design system for the Studio (brought into the repository as [`docs/design-system.md`](../design-system.md)): a warm-stone light theme with a slate dark theme, one crimson brand accent, gold for human accountability, blue for links and focus, Hanken Grotesk / Source Serif 4 / IBM Plex Mono self-hosted, 15px body, 14px cards, flat surfaces with hairlines, shadows on floating layers only, a motion set with a reduced-motion rule, a global focus ring, and an AA contrast contract enforced by a test.

## The Owner's Answers

1. **Scope.** The whole Studio: canvas, teach bar, drawer, dialogs, toasts, menus and the admin portal move to the design system's tokens, fonts and light-first theme. The reference stops being the visual target; it stays in the repository, read-only, untouched.
2. **Acceptance.** The redesigned screens become new screenshot baselines (same scenes and sizes, light and dark, win32 and linux), plus the design system's contrast test on the tokens. After that a visible change is a bug again.
3. **Branding.** The tokens and rules are taken as plain CSS custom properties in the Studio: crimson accent for brand chrome, selection and primary buttons; gold `--human` for human accountability (proposals awaiting approval, approve actions); blue for links, info and the focus ring; green success; red danger; warm-stone light by default with dark as the opt-in; the three typefaces through @fontsource; 15px body; 14px card radius; flat surfaces with hairlines, shadows only on floating layers; the motion set and the reduced-motion rule; the global focus ring. The Ontaix name and logo stay. No Tailwind migration, no seal mark, and no third-party product naming anywhere in product or code.

## Decision

### 1. Tokens Are the Contract

`apps/studio/src/design/tokens.css` is the single source of truth: raw light values in `:root`, raw dark values under `:root[data-theme="dark"]` and `.dark`, and an alias block that resolves the stylesheets' earlier names (`--panel`, `--ink`, `--ink-2`, `--ink-3`, `--line`, `--conflict`) onto the tokens. `design/base.css` holds typography, the global focus ring, selection, scrollbars, the motion set and the reduced-motion rule. `design/tokens.ts` mirrors what code needs (the font stacks, the default accent, a runtime `token()` reader with a light fallback map) and `tokens.test.ts` pins it to the CSS.

`contracts/design-tokens.json` describes these tokens instead of the reference's; its canvas, semantic and domain sections follow when the canvas moves to the tokens. A token value changes only in `tokens.css`, with a decision row and new baselines.

### 2. Light First, the Theme Switch Kept

Light is what a page shows before any setting loads. The Studio's existing theme switch stays as it is (admin portal, Appearance, `Light mode`; `setTheme()` in the store), setting `data-theme` on `<html>`; the in-browser mock starts tenants light with the crimson accent. The API's tenant defaults (`theme` `dark`, `accent` `#3fb8a9` in `contracts/schema.sql` and `apps/api/app/services/appearance_service.py`) are a schema and service change outside the Studio, listed under Consequences.

### 3. Three Guards Replace the Reference Comparison

- `contrast.test.ts` checks the AA pairs of the design system in both themes, with a two-way `KNOWN_BELOW_AA` ledger.
- `rawColours.test.ts` bans raw hex, `rgb()`, `rgba()` and `hsl()` outside `src/design/**`, with a `RESTYLE_PENDING` ledger that each restyle pull request drains.
- The screenshot suite compares every scene with a stored baseline under `tests/screenshots/baselines` (one image per scene, theme, viewport and platform) at 0.1 percent tolerance, through Playwright's `toHaveScreenshot`, and no longer renders the reference. The harness drops the stylesheets that hid the Studio's own elements from the reference; every element the product renders is in its baseline.

### 4. Delivery in Three Pull Requests

Foundations (tokens, fonts, base rules, the guards, the harness switch, the documents) first; the shell, dialogs, drawer, menus, toasts, teach bar, panel and admin portal second; the canvas third. Each regenerates the baselines of the scenes it changes.

## Consequences

- `CLAUDE.md`'s "one rule" names the design system as the visual source of truth and the reference as the historical origin of the Studio's behaviour and markup. `docs/ui-contract.md` keeps every behavioural rule and describes the baseline acceptance.
- The API's tenant appearance defaults follow (decision row 171): `tenant_settings.theme` defaults to `light`, `tenant_settings.accent` to `#d30c55`, the `domain_template` rows take the categorical palette, through migration 0011, which changes defaults and reference rows only and never a tenant's saved choices or its `tenant_domain` copies. The Studio applies a tenant accent only when it differs from the design system's default.
- `contracts/design-tokens.json` stops being "verbatim from the reference"; `docs/contracts.md` says so.
- The reference's Sora files under `tests/screenshots/fonts` are gone; the fonts ship with the build.
