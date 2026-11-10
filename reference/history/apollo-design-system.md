# Apollo Portal — Design System

> **Source of truth:** [`web/src/design/tokens.css`](web/src/design/tokens.css). This document describes it; if the two disagree, the CSS wins.
> Related: [`ACCESSIBILITY.md`](ACCESSIBILITY.md) (contrast ledger), [`PORTAL-ENGINEERING-GUIDE.md`](PORTAL-ENGINEERING-GUIDE.md).

The portal's visual language is **"autonomy under seal"**. It uses a calm, warm-stone neutral canvas with **one brand accent**, plus a small set of colours whose meaning is fixed. Colour in this portal carries meaning. A colour tells the reader *who* is acting, not only how important something is.

---

## 1. Principles

1. **Semantic tokens only.** Components style through role names (`bg-surface`, `text-human-text`, `border-line`). Raw Tailwind colour scales (`bg-blue-500`, `text-white`), arbitrary hex (`bg-[#fff]`) and hex/rgb in inline `style` are **banned**. ESLint ([`web/eslint.config.js`](web/eslint.config.js)) and the CI grep in `pipelines/ci.yml` enforce this (PNFR9). Only `src/design/**` may hold raw hex.
2. **Colour = meaning (Decision A).**
   | Colour | Role | Use for | Never use for |
   |---|---|---|---|
   | **Crimson** `--accent` | Brand chrome | Active/selected state, emphasis, primary buttons, brand links | Human-accountability signals |
   | **Gold** `--human` | Human accountability | HITL, approvals, "needs you", decisions recorded under a person's name | Generic highlight or decoration |
   | **Blue** `--link` / `--info` | Links, info, machine telemetry | Hyperlinks, info callouts, "live" machine status, the focus ring | Brand emphasis |
   | **Green** `--good` | Success | Healthy / completed / passed | — |
   | **Red** `--danger` | Failure / destructive | Errors, rejections, destructive actions | Brand emphasis (crimson is not danger) |
3. **One rebrand seam.** To re-skin the portal for a client, edit **only** the raw values in the `:root` and `.dark` blocks (and optionally the `--font-*` families). Never touch the `@theme` map or any component. The role names are the stable contract. `--accent` can be set per tenant (Decision C; the default is crimson).
4. **Accessible by construction.** Text tokens are ratio-checked in both themes by [`contrast.test.ts`](web/src/design/contrast.test.ts). A rebrand that drops a pair below its threshold fails the build (§9).
5. **Light is the default.** The warm-stone light theme is the v2 default. Dark is an opt-in `.dark` class on `<html>`.

---

## 2. Architecture

```
tokens.css
├── :root { --bg … }          ← raw LIGHT values   (rebrand seam)
├── .dark { --bg … }          ← raw DARK overrides (rebrand seam)
├── :root { --panel: var(--surface) … }   ← v1 aliases (follow .dark automatically)
└── @theme inline { --color-bg: var(--bg) … }  ← Tailwind v4 map → utilities (bg-bg, text-text-2, …)
```

- **Tailwind v4, CSS-first.** There is no `tailwind.config.*`. Tailwind is imported once in [`web/src/index.css`](web/src/index.css), which then imports `tokens.css`. Don't add a second `@import "tailwindcss"` to `tokens.css`.
- **Each `--color-X` becomes a utility for every property**: `bg-X`, `text-X`, `border-X`, `ring-X`, `fill-X`, … Because the canonical neutral is named `--text`, the utilities read `text-text`, `text-text-2`, `border-border` and so on.
- **The dark mode wiring** in `index.css` is `@custom-variant dark (&:where(.dark, .dark *));`. Without this line, Tailwind v4 binds `dark:` to `prefers-color-scheme` and silently ignores the class. Keep it.
- **The theme toggle** is `applyTheme()` in [`web/src/stores/uiStore.ts`](web/src/stores/uiStore.ts). It toggles `.dark` on `document.documentElement`. Light theme is simply the *absence* of `.dark`; there is no `.light` rule. `index.html` seeds `class="light"` to avoid a flash of the wrong theme. The theme lives in memory only (SEC-009: no localStorage).

---

## 3. Colour tokens

Every token below exists both as a CSS custom property (`var(--surface)`) and as a Tailwind colour (`bg-surface`).

### 3.1 Neutrals — surfaces

Light is **warm stone**; dark is **cool slate**.

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` | `#f5f5f5` | `#1b1f2a` | App canvas, the page background |
| `--surface` | `#ffffff` | `#232936` | Cards, panels, drawers, tooltips |
| `--surface-2` | `#f3f1ef` | `#2a3140` | Recessed / secondary surface, inset areas |
| `--hover` | `#f6f4f2` | `#2a3140` | Hover fill for interactive items |
| `--rowhover` | `#faf9f8` | `#272e3a` | Table / list row hover (subtler than `--hover`) |
| `--chip` | `#f3f1ef` | `#2c333f` | Chips, tags, the user's chat bubble |
| `--subtle` | `#fcfbfa` | `#20252f` | Barely-there fill (zebra, quiet wells) |
| `--scrim` | `rgba(20,22,31,.38)` | `rgba(0,0,0,.55)` | Modal / drawer backdrop (`bg-scrim`) |

### 3.2 Neutrals — borders

| Token | Light | Dark | Role |
|---|---|---|---|
| `--border` | `#edeae7` | `#363d4c` | Default hairline, ledger rules, chart grid |
| `--border-strong` | `#e5e1dd` | `#434b5c` | Inputs, emphasised dividers, scrollbar thumb |
| `--border-faint` | `#f0edea` | `#2c323f` | Very quiet internal separators |

### 3.3 Neutrals — text

| Token | Light | Dark | Role | AA on neutrals? |
|---|---|---|---|---|
| `--text` | `#2b2724` | `#f3f5f9` | Primary text, headings | ✅ |
| `--text-2` | `#57534e` | `#c6cbd6` | Secondary text, body copy in dense UI | ✅ |
| `--text-3` | `#6f6a64` | `#9aa2b1` | Tertiary: captions, meta, axis labels | ✅ (≥ 4.75:1 in light since Story 10.4) |
| `--text-4` | `#a8a29c` | `#6f7788` | Disabled / decorative only | ❌ Not for meaningful text (A11Y-C1) |

### 3.4 Brand accent — crimson (chrome only)

| Token | Light | Dark | Role |
|---|---|---|---|
| `--accent` | `#d30c55` | `#ff5c8a` | Primary button fill, active indicator, selected border |
| `--accent-strong` | `#b00a47` | `#ff85a8` | Hover/pressed state of accent fills |
| `--accent-soft` | `#fce1eb` | `#3a1420` | Selected-row tint, accent badge background, `::selection` |
| `--accent-text` | `#a80a44` | `#ff9fbb` | Accent-coloured text, especially on `--accent-soft` |

### 3.5 Human accountability — gold

| Token | Light | Dark | Role |
|---|---|---|---|
| `--human` | `#a07621` | `#e8b54d` | HITL / approval marker, seal, "needs you" fill |
| `--human-bright` | `#c8963a` | `#f2c766` | Highlight / hover of gold |
| `--human-soft` | `#f1e4c3` | `#362c18` | Approval card / banner tint |
| `--human-text` | `#7a5a19` | `#e8b54d` | Gold text; also the gold primary-button fill (OQ21) |

> ⚠️ **Do not "fix" the light `--human`.** `#a07621` is deliberately darker than the dark-theme `#e8b54d`, so it holds contrast on a light surface. Never put `#e8b54d` on white.

### 3.6 Links & info — blue

| Token | Light | Dark | Role |
|---|---|---|---|
| `--link` | `#2563eb` | `#8fb2ff` | Hyperlinks, the **focus ring**, "live" telemetry |
| `--link-hover` | `#1d4ed8` | `#b4ccff` | Link hover |
| `--info` | `#1d4ed8` | `#9cb8ff` | Info icon / emphasis |
| `--info-bg` | `#f4f8ff` | `#1c2536` | Info callout background |
| `--info-border` | `#d7e4fb` | `#2f3b54` | Info callout border |
| `--info-text` | `#334768` | `#c6d4f0` | Text inside info callouts |
| `--info-chip` | `#dce7fb` | `#28344c` | Info chip / tag background |

### 3.7 Status

| Token | Light | Dark | Role |
|---|---|---|---|
| `--good` | `#0e8a6a` | `#4db3a4` | Success icon / indicator |
| `--good-soft` | `#dcf0e9` | `#17322d` | Success tint |
| `--danger` | `#c0181d` | `#e5736b` | Error, rejection, destructive action |
| `--danger-soft` | `#fbe9e9` | `#3a2420` | Error tint |

> Light `--good` as body text is below AA (A11Y-C2). Prefer it for icons, dots and badges, or pair it with a label in `--text`.

### 3.8 Pairing rules (quick reference)

| Pattern | Background | Foreground |
|---|---|---|
| Accent badge / selected | `bg-accent-soft` | `text-accent-text` |
| Approval / HITL banner | `bg-human-soft` | `text-human-text` |
| Info callout | `bg-info-bg` + `border-info-border` | `text-info-text` |
| Success badge | `bg-good-soft` | `text-good` |
| Error badge | `bg-danger-soft` | `text-danger` |
| Primary (brand) button | `bg-accent` → hover `bg-accent-strong` | `text-ground` |
| Primary (human / approve) button | `bg-human-text` | `text-ground` (not on `bg-human` — A11Y-C6) |
| Active nav item | `bg-chip` + a 3px `before:bg-accent` bar on the left | `text-text` |

---

## 4. v1 aliases (legacy vocabulary)

The v1 "Helios / Meridian" names are kept as **aliases**. They resolve through `var()` onto the v2 tokens, so they follow the theme automatically. They are still common in the codebase (`text-muted` has around 150 uses). **Prefer the canonical name in new code.**

| v1 utility / var | Resolves to | Note |
|---|---|---|
| `ground` | `--bg` | |
| `panel` / `panel-2` | `--surface` / `--surface-2` | |
| `line` / `line-strong` | `--border` / `--border-strong` | |
| `muted` (`--text-muted`) | `--text-2` | |
| `faint` (`--text-faint`) | `--text-3` | |
| `faint-2` | `--text-4` | Utility only |
| `helios` / `-bright` / `-soft` | `--human*` | **Gold** |
| `meridian` / `-bright` / `-soft` | `--accent`, `--accent-strong`, `--accent-soft` | ⚠️ **Now crimson**, no longer blue (Decision A collapse). If a "machine/live" surface must stay blue, use `link`. |
| `verdigris` / `-soft` | `--good*` | |
| `ember` / `-soft` | `--danger*` | |
| `seal` | `--human` | Don't use `text-seal`. Colour the seal with `text-helios` / `text-human`. |

---

## 5. Typography

Fonts are self-hosted through `@fontsource` (imported in `web/src/main.tsx`), so the portal makes no external font requests.

| Token / utility | Family | Use |
|---|---|---|
| `--font-sans` (default) | **Hanken Grotesk Variable** → system-ui | All UI text |
| `--font-display` / `font-display` | Hanken Grotesk Variable | Headings, page titles, KPI numerals |
| `--font-serif` / `font-serif` | **Source Serif 4 Variable** → Georgia | Rare editorial accents (quotes, narrative) |
| `--font-mono` / `font-mono` | **IBM Plex Mono** 400/500 | IDs, hashes, trace refs, code, timestamps |

**Base body:** `15px` (`0.9375rem`), line-height `1.55`, optical sizing auto, antialiased.

**Type scale.** Tailwind's default scale is used, plus one custom step:

| Utility | Size | Typical use |
|---|---|---|
| `text-2xs` | 11px (`0.6875rem`) | **The most used size.** Eyebrows, meta, chip labels, table captions |
| `text-xs` | 12px | Secondary meta, dense table cells |
| `text-sm` | 14px | Controls, dense body |
| `text-[13.5px]`–`text-[17px]` | — | Fine-tuned body/title sizes in specific components (arbitrary values are allowed for size, not for colour) |
| `text-base` → `text-xl` | 16–20px | Section and page headings |

**Numerals:** add `.tnum` (tabular-nums) to any column of figures or live counter so digits don't shift.

---

## 6. Shape, elevation & layout

| Token / utility | Value | Use |
|---|---|---|
| `--radius-card` / `rounded-card` | **14px** | Cards and panels (the house radius; `rounded-[14px]` is the same) |
| `rounded-md` / `rounded-lg` / `rounded-xl` | 6 / 8 / 12px | Inputs, buttons, inner tiles |
| `rounded-full` | — | Chips, pills, avatars, status dots (the most used radius) |
| Focus outline radius | 4px | Set globally on `:focus-visible` |

**Elevation** is mostly flat: surfaces are separated by `border-line` hairlines and the `bg`/`surface` step, not by shadows. Shadows are reserved for floating layers: `shadow-2xl` for drawers and modals, `shadow-lg`/`shadow-xl` for popovers and the FAB.

**Ledger ruling:** `.ledger-rows > *` draws a `1px solid var(--border)` between rows, with none after the last row. Use it **only** inside table/ledger widgets.

**Scrollbars:** 10px, with a `--border-strong` thumb (6px radius, 2px `--bg` border) on a transparent track. `.no-scrollbar` hides them.

**Selection:** `::selection` uses `--accent-soft` / `--accent-text`.

---

## 7. Motion

All animations use one of two eases: an **expressive out-curve** `cubic-bezier(0.2, 0.8, 0.3, 1)` for entrances, or plain `ease`. Charts animate for 350ms.

| Utility | Duration / curve | Keyframes | Use |
|---|---|---|---|
| `animate-rise` | 280ms expressive | fade + 6px up | **Default entrance** for cards and list items |
| `animate-fade-up` | 240ms ease | fade + 8px up | Popovers, toasts, inline reveals |
| `animate-slide-l` | 240ms ease | fade + 40px from right | Drawers and side panels |
| `animate-boot` | 480ms expressive | fade + 14px from left, brightness 2→1 | One-off "system boot" moment |
| `animate-breathe` | 2.8s loop | scale 1→1.65, opacity pulse | "Live" / listening indicator halo |
| `animate-fab-float` | 3.4s loop | 5px bob | Floating action button idle |
| `animate-fab-pulse` | 2.6s loop | ripple out to 2× | FAB attention ring |
| `animate-caret` | 1s steps(2) loop | blink | Streaming-text caret |

**Reduced motion:** under `prefers-reduced-motion: reduce`, every animation and transition is collapsed to 0.01ms and runs once. Don't override this.

---

## 8. Focus

- **Global ring:** `:focus-visible { outline: 2.5px solid var(--link); outline-offset: 2px; border-radius: 4px; }`.
- This rule is **unlayered**, so it beats Tailwind's `outline-none` (utilities live in `@layer utilities`). This is intentional, and `focusRing.test.ts` guards it.
- **Opt-out:** a control that draws its own focus affordance adds the attribute `data-focus-ring="none"` (an attribute, not a class, so a utility refactor can't sweep it up). It then **must** show focus another way, for example the chat composer lights its container with `focus-within:`. Removing focus outright is an accessibility regression.

---

## 9. Accessibility contract (WCAG-AA, PNFR9 / Story 10.4)

[`contrast.test.ts`](web/src/design/contrast.test.ts) reads `tokens.css` from disk and resolves `var()` chains per theme. It then checks these pairs in **both** themes:

- `--text`, `--text-2`, `--text-3` ≥ **4.5:1** on every neutral surface (`bg`, `surface`, `surface-2`, `hover`, `rowhover`, `chip`, `subtle`)
- each status text on its own tint (`good/good-soft`, `human-text/human-soft`, `accent-text/accent-soft`, `danger/danger-soft`)
- the gold primary pair
- `--link` (the focus outline) ≥ **3:1**

Pairs already below AA are recorded in `KNOWN_BELOW_AA` and in `ACCESSIBILITY.md`. The ledger works in two directions: an unlisted pair that fails breaks the build, and a listed pair that starts *passing* also breaks the build until its row is removed.

| Ledger id | Pair | Guidance |
|---|---|---|
| A11Y-C1 | `--text-4` on any neutral (both themes) | Decorative/disabled only |
| A11Y-C2 | Light `--good` as text | Icons/dots, or pair with a `--text` label |
| A11Y-C3 | Light `--human` as text | Use `--human-text` for gold text |
| A11Y-C4 | Dark `--accent` / `--danger` on `--surface-2` | Avoid; put on `--surface` |
| A11Y-C5 | `--text-3` on `-soft` tints | Not used today; use the tint's `-text` token |
| A11Y-C6 | `text-ground` on `bg-human` | Only the Topbar bell badge remains |

---

## 10. Data visualisation

ECharts styling comes from the tokens **at runtime** in [`echartsTheme.ts`](web/src/design/echartsTheme.ts). Charts therefore follow a rebrand and the `.dark` toggle automatically, and ECharts' default colours never appear. If a variable is missing, a light-theme hex fallback applies so a series never renders blank.

- **Categorical order:** `accent → link → good → human → text-3 → violet #7c3aed`. Blue sits second so crimson and the warm danger red are never adjacent.
- **Chrome:** chart font Hanken Grotesk 11px in `--text-2`. Axis labels are 10px `--text-3`. Axis line and dashed y-split use `--border`. Tooltips use `--surface` with a `--border` edge and `--text` text.
- **Counting series** ([`chartScales.ts`](web/src/design/chartScales.ts)): an all-integer series gets `minInterval: 1` (no "0.5 decisions"). An all-UTC-midnight series is labelled as days (`08 Sep`), never as instants. Series with ≤ 40 points (`SPARSE_SERIES`) show markers.

---

## 11. Iconography — the Trace Seal

[`TraceSeal.tsx`](web/src/design/TraceSeal.tsx) is the brand mark: a ring with a centre dot and eight rays, drawn with `currentColor` on a 24×24 viewBox. It defaults to 14px and is `aria-hidden`. Colour it with a token utility, normally `text-helios` / `text-human`, because the seal stands for human accountability.

The favicon `public/seal.svg` is a **known exception**: browsers don't apply page CSS to icons, so its gold is hard-coded hex and won't follow a rebrand.

---

## 12. Embedded SDK chat kit

The governed conversation (`@apollo/sdk/chat <ChatStream>`) is themed through its `--obs-*` variables. These are remapped in `index.css` under `.apollo-chat`, at variable level only, never through SDK class names:

| SDK var | Portal token | Meaning |
|---|---|---|
| `--obs-surface-0` | `--panel` | Drawer base |
| `--obs-surface-2` | `--ground` | Composer input + agent bubble (recessed) |
| `--obs-surface-3` | `--chip` | The user's own message bubble (neutral) |
| `--obs-electric` / `-bright` | `--accent` / `--accent-strong` | Send button (chrome → crimson) |
| `--obs-text-400` | `--text-faint` | Placeholder, muted captions |
| `--obs-line-1` | `--line` | Input / hairline borders |

---

## 13. Rebranding a client — checklist

1. Edit raw hex values in `:root` (light) and `.dark` (dark) in `tokens.css`. To change typefaces, also edit `--font-*` in `@theme` and the `@fontsource` imports in `main.tsx`.
2. Keep the **meaning** of each colour: the accent is the client brand; gold stays human accountability; blue stays links/info.
3. Update the `FALLBACK` hex map in `echartsTheme.ts` to the new light values.
4. Run `npm test` in `web/`. `contrast.test.ts` must pass, and any `KNOWN_BELOW_AA` row that changed must be updated together with `ACCESSIBILITY.md`.
5. Accept that `public/seal.svg` (the favicon) needs a manual edit.
