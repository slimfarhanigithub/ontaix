# Ontaix Studio

React 19 + TypeScript + Vite, tested with vitest and a Playwright screenshot suite. The Studio must be identical to `reference/ontaix-studio-reference.html`; read `docs/ui-contract.md` before changing anything here. The canvas renderer is ported verbatim from the reference: every module under `src/canvas` names the reference line range it comes from, and no constant, easing, colour or threshold in them may change.

## Layout

```text
index.html                 Vite entry document, Sora from Google Fonts as in the reference
src/
  main.tsx                 seeds the random source (?seed=<n>), installs the mock API, mounts <App />
  App.tsx                  the shell, in the reference's element order
  styles/reference.css     the reference stylesheet, copied verbatim
  runtime/
    rng.ts                 the one random source (crypto, or mulberry32 in test mode)
    clock.ts               the one clock (performance.now, Date)
  canvas/                  verbatim renderer modules
    constants.ts themes.ts colour.ts types.ts view.ts
    state.ts               nodes, links, companies, domains and the model helpers
    division.ts physics.ts hulls.ts regions.ts links.ts labels.ts neck.ts cells.ts
    focus.ts arrange.ts lineage.ts
    renderer.ts            frame loop and pointer interactions
  api/
    types.ts               shapes from contracts/openapi.yaml
    client.ts              typed fetch client (VITE_ONTAIX_API_URL, default /api/v1)
    events.ts              live-update bus in the envelope of contracts/events.yaml
    mock/                  in-browser API over an in-memory store seeded from the reference constants
  store/store.ts           scene state, shell state and actions; applies live events to the canvas
  demo/                    scene list and the scripted story (proposals through the API)
  nl/suggest.ts            suggest-action tables
  shell/                   React components producing the reference DOM
test-support/playwright.ts re-exports the screenshot suite's dependencies for tests/screenshots
```

## Run Locally

From the repository root:

```bash
pnpm install
pnpm --filter studio dev            # http://localhost:5173, mock API in the browser
pnpm --filter studio test           # vitest
pnpm --filter studio build
pnpm --filter studio test:screens   # Playwright: reference vs Studio at 1440x900, dark and light
```

`pnpm exec playwright install chromium` (inside `apps/studio`) fetches the browser the screenshot suite needs once. The suite builds the Studio with the test hooks, serves it on port 4787, renders each scene from the reference file and from the Studio under the same seed and fake clock at 1440x900 and 1920x1080 in both themes, compares pixel for pixel, and writes `reference.png`, `studio.png` and `diff.png` per scene into `tests/screenshots/output/`.

## Test Mode

Test hooks exist only in dev builds or when `VITE_ONTAIX_TEST_HOOKS=true` is set at build time; the screenshot suite builds with the flag, the Dockerfile does not. With the hooks on, `?seed=<n>` (or `VITE_ONTAIX_SEED`) switches the random source to a seeded generator and exposes `window.__ontaix` (store and draw log), and `?api=mock` forces the in-browser API, which is also the default when `VITE_ONTAIX_API_URL` is unset. The seeded generator and the mock are loaded on demand, so a production build without the flag does not contain them. `<html data-ontaix-ready="ready">` is set once the scene has loaded.

Proposal text from the API (`html`) is passed through an allow-list sanitiser (`b`, `i`, `em`, `span.class`) before it is injected; every other string from the model is rendered as text.
