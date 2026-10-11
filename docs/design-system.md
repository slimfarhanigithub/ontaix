# Ontaix Studio — Design System

> **Source of truth:** [`apps/studio/src/design/tokens.css`](../apps/studio/src/design/tokens.css). This document describes it; if the two disagree, the CSS wins.
> Related: [`ui-contract.md`](ui-contract.md) (what the screenshot suite accepts), [`adr/0019-design-system.md`](adr/0019-design-system.md) (why the Studio moved to it), decision row 163.

The Studio's visual language is a calm, warm-stone neutral canvas with **one brand accent**, plus a small set of colours whose meaning is fixed. Colour in the Studio carries meaning: it tells the reader *who* is acting, not only how important something is.

## 1. Principles

1. **Semantic tokens only.** Stylesheets and components style through role names (`var(--surface)`, `var(--human-text)`, `var(--border)`). Raw hex, `rgb()`, `rgba()` and `hsl()` values are banned outside `apps/studio/src/design/`; [`rawColours.test.ts`](../apps/studio/src/design/rawColours.test.ts) enforces it, with a `RESTYLE_PENDING` ledger for the files still being moved onto the tokens. Canvas fills and SVG attributes read the tokens at runtime through [`tokens.ts`](../apps/studio/src/design/tokens.ts) (`token()`), with a fallback so nothing renders blank.
2. **Colour = meaning.**
   | Colour | Role | Use for | Never use for |
   |---|---|---|---|
   | **Crimson** `--accent` | Brand chrome | Active/selected state, emphasis, primary buttons, the pressed tool | Human-accountability signals |
   | **Gold** `--human` | Human accountability | Proposals awaiting approval, Approve actions, "needs you", decisions recorded under a person's name | Generic highlight or decoration |
   | **Blue** `--link` / `--info` | Links, info, machine telemetry | Hyperlinks, info callouts, "live" machine status, the focus ring | Brand emphasis |
   | **Green** `--good` | Success | Healthy / approved / passed / connected | — |
   | **Red** `--danger` | Failure / destructive | Errors, rejections, refusals, conflicts, destructive actions | Brand emphasis (crimson is not danger) |
3. **One rebrand seam.** To re-skin the Studio, edit **only** the raw values in the `:root` block of `tokens.css` (and optionally the `--font-*` families). Never touch the alias block or any component. The role names are the stable contract. A tenant may set `--accent` from the admin portal's Appearance page; the default is crimson.
4. **Accessible by construction.** Text tokens are ratio-checked by [`contrast.test.ts`](../apps/studio/src/design/contrast.test.ts). A rebrand that drops a pair below its threshold fails the build (Section 9).
5. **One theme.** The warm-stone light theme is the Studio's only theme: every page, the canvas and the admin portal show it, and there is no theme switch and no dark mode (owner decision, 2026-10-11).

## 2. Architecture

```mermaid
flowchart TD
  tokens["tokens.css<br/>:root raw values (rebrand seam)<br/>alias block: --panel, --ink, --ink-2, --ink-3, --line, --conflict"]
  base["base.css<br/>typography, focus ring, selection, scrollbars, motion, reduced motion"]
  fonts["@fontsource imports in main.tsx<br/>Hanken Grotesk Variable, Source Serif 4 Variable, IBM Plex Mono"]
  styles["styles/reference.css, studio.css, admin-rows.css<br/>component rules, tokens only"]
  code["tokens.ts<br/>FONT_SANS, FONT_MONO, DEFAULT_ACCENT, token(), LIGHT_FALLBACK"]
  canvas["canvas renderer and SVG icons<br/>read tokens at runtime"]
  tokens --> base --> styles
  fonts --> base
  tokens -. mirrored, pinned by tokens.test.ts .-> code --> canvas
```

- **Plain CSS custom properties.** There is no utility framework; every rule writes `var(--name)`. `main.tsx` imports the fonts, then `design/tokens.css`, then `design/base.css`, then the component stylesheets, so a component rule of equal specificity wins where it sets its own value.
- **No theme attribute.** `:root` carries the one theme and `color-scheme: light`; nothing on `<html>` selects a theme, and the tenant's appearance holds no theme. A tenant's accent and source colour are the only values a page applies on `<html>`.
- **The earlier vocabulary** (`--panel`, `--ink`, `--ink-2`, `--ink-3`, `--line`, `--conflict`) resolves onto the tokens in the alias block, so every existing rule follows a rebrand. New rules use the canonical names.

## 3. Colour Tokens

Every token below is a CSS custom property (`var(--surface)`).

### 3.1 Neutrals — Surfaces

The surfaces are **warm stone**.

| Token | Value | Role |
|---|---|---|
| `--bg` | `#f5f5f5` | The canvas and the page background |
| `--surface` | `#ffffff` | Cards, panels, the drawer, dialogs, tooltips, the teach bar |
| `--surface-2` | `#f3f1ef` | Recessed / secondary surface, inset areas, inputs |
| `--hover` | `#f6f4f2` | Hover fill for interactive items |
| `--rowhover` | `#faf9f8` | Table / list row hover (subtler than `--hover`) |
| `--chip` | `#f3f1ef` | Chips, tags, the active navigation item |
| `--subtle` | `#fcfbfa` | Barely-there fill (zebra, quiet wells) |
| `--scrim` | `rgba(20,22,31,.38)` | Modal / drawer / admin portal backdrop |

### 3.2 Neutrals — Borders

| Token | Value | Role |
|---|---|---|
| `--border` | `#edeae7` | Default hairline, ledger rules, dividers |
| `--border-strong` | `#e5e1dd` | Inputs, emphasised dividers, the scrollbar thumb |
| `--border-faint` | `#f0edea` | Very quiet internal separators |

### 3.3 Neutrals — Text

| Token | Value | Role | AA on neutrals? |
|---|---|---|---|
| `--text` | `#2b2724` | Primary text, headings | Yes |
| `--text-2` | `#57534e` | Secondary text, body copy in dense UI | Yes |
| `--text-3` | `#6f6a64` | Tertiary: captions, meta, eyebrows | Yes (4.75:1 or better in light) |
| `--text-4` | `#a8a29c` | Disabled / decorative only | No. Not for meaningful text (A11Y-C1) |

### 3.4 Brand Accent — Crimson (Chrome Only)

| Token | Value | Role |
|---|---|---|
| `--accent` | `#d30c55` | Primary button fill, active indicator, selected border, pressed tool, the wordmark dot |
| `--accent-strong` | `#b00a47` | Hover / pressed state of accent fills |
| `--accent-soft` | `#fce1eb` | Selected-row tint, accent badge background, `::selection` |
| `--accent-text` | `#a80a44` | Accent-coloured text, especially on `--accent-soft` |

### 3.5 Human Accountability — Gold

| Token | Value | Role |
|---|---|---|
| `--human` | `#a07621` | Pending marker, "needs you" fill, the pending dot |
| `--human-bright` | `#c8963a` | Highlight / hover of gold |
| `--human-soft` | `#f1e4c3` | Approval card / banner tint, the pending proposal row |
| `--human-text` | `#7a5a19` | Gold text; also the gold primary-button fill (Approve, Approve all) |

> **Do not "fix" `--human`.** `#a07621` is deliberately deep so it holds contrast on a light surface. Never put a bright gold such as `#e8b54d` on white.

### 3.6 Links and Info — Blue

| Token | Value | Role |
|---|---|---|
| `--link` | `#2563eb` | Hyperlinks, the **focus ring**, "live" telemetry |
| `--link-hover` | `#1d4ed8` | Link hover |
| `--info` | `#1d4ed8` | Info icon / emphasis |
| `--info-bg` | `#f4f8ff` | Info callout background |
| `--info-border` | `#d7e4fb` | Info callout border |
| `--info-text` | `#334768` | Text inside info callouts |
| `--info-chip` | `#dce7fb` | Info chip / tag background |

### 3.7 Status

| Token | Value | Role |
|---|---|---|
| `--good` | `#0e8a6a` | Success icon / indicator, the approval rim |
| `--good-soft` | `#dcf0e9` | Success tint |
| `--danger` | `#c0181d` | Error, rejection, refusal, conflict, destructive action |
| `--danger-soft` | `#fbe9e9` | Error tint |
| `--violet` | `#7c3aed` | Categorical colour 6 |
| `--teal` | `#0e7490` | Categorical colour 7 |
| `--orange` | `#c2410c` | Categorical colour 8 |
| `--olive` | `#4d7c0f` | Categorical colour 9 |
| `--source` | `#d6bd8a` | Data sources on the canvas (squares, binding lines), drawn only when a scene carries a source; tenant-settable; shapes only, never text |

> `--good` as body text is below AA (A11Y-C2). Prefer it for icons, dots and badges, or pair it with a label in `--text`.

### 3.8 Pairing Rules (Quick Reference)

| Pattern | Background | Foreground |
|---|---|---|
| Accent badge / selected | `--accent-soft` | `--accent-text` |
| Approval / pending banner | `--human-soft` | `--human-text` |
| Info callout | `--info-bg` + `--info-border` | `--info-text` |
| Success badge | `--good-soft` | a `--good` dot or icon with the label in `--text` |
| Error badge | `--danger-soft` | `--danger` |
| Primary (brand) button | `--accent`, hover `--accent-strong` | `--bg` |
| Primary (human / approve) button | `--human-text` | `--bg` (not on `--human`, A11Y-C6) |
| Active nav item | `--chip` + a 3px `--accent` bar on the left | `--text` |

## 4. Earlier Vocabulary (Aliases)

The names the Studio's stylesheets grew up with are kept as **aliases**. They resolve through `var()` onto the tokens, so they follow a rebrand automatically. **Prefer the canonical name in new code.**

| Alias | Resolves to | Note |
|---|---|---|
| `--panel` | `--surface` | Was a translucent dark panel; now an opaque surface |
| `--ink` / `--ink-2` / `--ink-3` | `--text` / `--text-2` / `--text-3` | |
| `--line` | `--border` | |
| `--conflict` | `--danger` | |
| `--accent` | itself | **Now crimson**, no longer teal. Approvals use gold, not the accent |

## 5. Typography

Fonts are self-hosted through `@fontsource` (imported in `apps/studio/src/main.tsx`), so the Studio makes no external font request.

| Token | Family | Use |
|---|---|---|
| `--font-sans` (default) | **Hanken Grotesk Variable**, then system-ui | All UI text; the canvas labels (`FONT_SANS` in `tokens.ts`) |
| `--font-display` | Hanken Grotesk Variable | Headings, page titles, KPI numerals |
| `--font-serif` | **Source Serif 4 Variable**, then Georgia | Rare editorial accents (quotes, narrative) |
| `--font-mono` | **IBM Plex Mono** 400/500 | Ids, hashes, column paths, code, timestamps |

**Base body:** `15px`, line-height `1.55`, optical sizing auto, antialiased.

**Type scale.** Component sizes stay as the stylesheets set them (11px eyebrows and meta, 12 to 13.5px controls and dense body, 14 to 20px titles). Arbitrary values are allowed for size, not for colour.

**Numerals:** add `.tnum` (tabular-nums) to any column of figures or live counter so digits never shift.

## 6. Shape, Elevation and Layout

| Token / class | Value | Use |
|---|---|---|
| `--radius-card` | **14px** | Cards and panels (the house radius) |
| `--radius-md` / `--radius-lg` / `--radius-xl` | 6 / 8 / 12px | Inputs, buttons, inner tiles |
| `--radius-full` | 999px | Chips, pills, avatars, status dots |
| Focus outline radius | 4px | Set globally on `:focus-visible` |

**Elevation** is mostly flat: surfaces are separated by `--border` hairlines and the `--bg` / `--surface` step, not by shadows. Shadows are reserved for floating layers: `--shadow-float` for the drawer, dialogs and the admin window, `--shadow-pop` for popovers, menus and toasts.

**Ledger ruling:** `.ledger-rows > *` draws a `1px solid var(--border)` between rows, with none after the last row. Use it **only** inside table / ledger widgets.

**Scrollbars:** 10px, with a `--border-strong` thumb (6px radius, 2px `--bg` border) on a transparent track. `.no-scrollbar` hides them.

**Selection:** `::selection` uses `--accent-soft` / `--accent-text`.

## 7. Motion

All animations use one of two eases: an **expressive out-curve** `cubic-bezier(0.2, 0.8, 0.3, 1)` (`--ease-expressive`) for entrances, or plain `ease`. The canvas keeps its own clock-driven motion (division, recoil, drift), which these classes do not touch.

| Class | Duration / curve | Keyframes | Use |
|---|---|---|---|
| `animate-rise` | 280ms expressive | fade + 6px up | **Default entrance** for cards and list items |
| `animate-fade-up` | 240ms ease | fade + 8px up | Popovers, toasts, inline reveals |
| `animate-slide-l` | 240ms ease | fade + 40px from right | Drawers and side panels |
| `animate-boot` | 480ms expressive | fade + 14px from left, brightness 2 to 1 | One-off "system boot" moment |
| `animate-breathe` | 2.8s loop | scale 1 to 1.65, opacity pulse | "Live" / listening indicator halo |
| `animate-fab-float` | 3.4s loop | 5px bob | Floating action button idle |
| `animate-fab-pulse` | 2.6s loop | ripple out to 2x | FAB attention ring |
| `animate-caret` | 1s steps(2) loop | blink | Streaming-text caret |

**Reduced motion:** under `prefers-reduced-motion: reduce`, every animation and transition is collapsed to 0.01ms and runs once. Don't override this.

## 8. Focus

- **Global ring:** `:focus-visible { outline: 2.5px solid var(--link); outline-offset: 2px; border-radius: 4px; }` in `base.css`. No component draws an accent ring of its own.
- **Opt-out:** a control that draws its own focus affordance adds the attribute `data-focus-ring="none"` (an attribute, not a class, so a refactor can't sweep it up). It then **must** show focus another way, for example by lighting its container with `:focus-within`. Removing focus outright is an accessibility regression.

## 9. Accessibility Contract (WCAG AA)

[`contrast.test.ts`](../apps/studio/src/design/contrast.test.ts) reads `tokens.css` from disk and resolves `var()` chains. It then checks these pairs:

- `--text`, `--text-2`, `--text-3` at **4.5:1** or better on every neutral surface (`bg`, `surface`, `surface-2`, `hover`, `rowhover`, `chip`, `subtle`)
- each status text on its own tint (`good/good-soft`, `human-text/human-soft`, `accent-text/accent-soft`, `danger/danger-soft`, `info-text/info-bg`)
- the gold and crimson primary pairs (`--bg` on `--human-text`, `--human`, `--accent`)
- `--link` (the focus outline) at **3:1** or better on every neutral

Pairs already below AA are recorded in `KNOWN_BELOW_AA` and below. The ledger works in two directions: an unlisted pair that fails breaks the build, and a listed pair that starts *passing* also breaks the build until its row is removed.

| Ledger id | Pair | Guidance |
|---|---|---|
| A11Y-C1 | `--text-4` on any neutral | Decorative / disabled only |
| A11Y-C2 | `--good` as text on neutrals | Icons / dots, or pair with a `--text` label |
| A11Y-C3 | `--human` as text on neutrals | Use `--human-text` for gold text |
| A11Y-C5 | `--text-3` on `--accent-soft` / `--human-soft` | Use the tint's own `-text` token |
| A11Y-C6 | `--bg` on `--human` | A gold fill under light text uses `--human-text`, never `--human` |
| A11Y-C7 | `--good` on `--good-soft` (3.6:1) | A success badge shows a `--good` dot or icon with its label in `--text` |

## 10. The Canvas

The canvas renderer reads its colours from the tokens **at runtime** through `token()` in [`tokens.ts`](../apps/studio/src/design/tokens.ts), so cells, hulls, links and labels follow a rebrand automatically. If a variable is missing, the fallback applies so nothing renders blank.

- **Categorical order** for domain products and series: `accent`, `link`, `good`, `human`, `text-3`, `violet`, `teal`, `orange`, `olive` (`CATEGORICAL` in `tokens.ts`). Blue sits second so crimson and the warm danger red are never adjacent. The nine domain templates take these nine in order; a new custom domain takes the first one no domain uses.
- **Stored colours are token values.** A domain's colour is stored as the value of its token (or a tenant's own hex); `themedColour()` draws a stored default with its token's value as the page applies it and a tenant's own colour as it is.
- **Theme object:** `canvas/themes.ts` derives the renderer's background, label inks, chip surface, label halo, vignette and hull colour from the tokens; only the hull and region alphas are fixed.
- **Labels:** Hanken Grotesk at the sizes the renderer sets, in `--text` and `--text-2`; chips on `--surface`.

## 11. Iconography

The wordmark is the Ontaix name with an accent dot. Icons are line icons drawn with `currentColor` on a 16x16 viewBox, so they take the colour of their text.

## 12. Rebranding a Tenant — Checklist

1. Edit the raw hex values in `:root` in `tokens.css`. To change typefaces, also edit `--font-*` and the `@fontsource` imports in `main.tsx`, and `FONT_SANS` / `FONT_MONO` in `tokens.ts`.
2. Keep the **meaning** of each colour: the accent is the brand; gold stays human accountability; blue stays links / info / focus.
3. Update `LIGHT_FALLBACK` in `tokens.ts` to the new values; `tokens.test.ts` pins it.
4. Run `pnpm --filter studio test`. `contrast.test.ts` must pass, and any `KNOWN_BELOW_AA` row that changed must be updated together with Section 9 above.
5. Regenerate the screenshot baselines (`ui-contract.md`, "Acceptance").
