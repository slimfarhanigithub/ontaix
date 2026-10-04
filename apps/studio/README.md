# Ontaix Studio

React 19 + TypeScript + Vite, tested with vitest and a Playwright screenshot suite. The Studio follows `docs/design-system.md` (source of truth `src/design/tokens.css`) and keeps every behaviour of `docs/ui-contract.md`; read both before changing anything here. The canvas renderer is ported from `reference/ontaix-studio-reference.html`: every module under `src/canvas` names the reference line range it comes from, and no easing or threshold in them may change; its colours and fonts come from the design tokens.

## Layout

```text
index.html                 Vite entry document; fonts are bundled through @fontsource (no external request)
src/
  main.tsx                 seeds the random source (?seed=<n>), installs the mock API, mounts <App />
  App.tsx                  the shell, in the reference's element order
  design/                  tokens.css (the design tokens), base.css (typography, focus, motion), tokens.ts, the contrast and raw-colour guards
  styles/reference.css     the component stylesheet grown from the reference, styled through the tokens
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
    session.ts             the session's CSRF token and the session-ended / password-change signals
    events.ts              live-update bus in the envelope of contracts/events.yaml
    real.ts                real-API wiring: responses replayed as live events
    mock/                  in-browser API over an in-memory store seeded from the reference constants;
                           its teach parser and document extraction mirror the API's
  store/store.ts           scene state, shell state and actions; applies live events to the canvas
  teach/teach.ts           text, speech transcripts and document imports through /teach/parse
  teach/azureSpeech.ts     Azure AI Speech recognition for the microphone (SDK loaded on first use)
  nl/parser.ts             rule-based teach grammar, used by the mock
  nl/suggest.ts            suggest-action tables
  shell/                   React components producing the reference DOM
  auth/                    session gate, sign-in and password pages, account controls (ADR 0017)
  platform/                the super admin's platform portal: organizations, users, audit log
test-support/playwright.ts re-exports the screenshot suite's dependencies for tests/screenshots
```

## Run Locally

From the repository root:

```bash
pnpm install
pnpm --filter studio dev            # http://localhost:5173, mock API in the browser
pnpm --filter studio test           # vitest
pnpm --filter studio build
pnpm --filter studio test:screens   # Playwright: every scene against its baseline, light and dark
pnpm dev:stack                      # Studio on http://127.0.0.1:5173 against the real API (see the root README)
pnpm --filter studio test:e2e       # Playwright: the Studio against the real API on the local stack
```

`pnpm exec playwright install chromium` (inside `apps/studio`) fetches the browser the screenshot suite needs once. The suite builds the Studio with the test hooks, serves it on port 4787, renders each scene under the same seed and fake clock at 1440x900 and 1920x1080 in both themes and compares it with its baseline under `tests/screenshots/baselines/` (`--update-snapshots` rewrites the baselines of the running platform); failures write the actual image and the diff into `tests/screenshots/output/`.

## Test Mode

Test hooks exist only in dev builds or when `VITE_ONTAIX_TEST_HOOKS=true` is set at build time; the screenshot suite builds with the flag, the Dockerfile does not. With the hooks on, `?seed=<n>` (or `VITE_ONTAIX_SEED`) switches the random source to a seeded generator and exposes `window.__ontaix` (store and draw log), and `?api=mock` forces the in-browser API, which is also the default when `VITE_ONTAIX_API_URL` is unset, and `?api=real` lets the network answer instead, so the screenshot suite can drive the sign-in, password and platform screens through Playwright routes (`tests/screenshots/auth.spec.ts`). The seeded generator and the mock are loaded on demand, so a production build without the flag does not contain them. `<html data-ontaix-ready="ready">` is set once the scene has loaded.

## Real API

With `VITE_ONTAIX_API_URL` set, the Studio talks to that API and `api/real.ts` wires it in. The API has no WebSocket hub yet, so each write's response is replayed on the live-event bus as the event the hub will send, and a bulk run (approve all, reject all) is followed by `snapshot.required`, which reloads `GET /scene`. Content enters as text typed in the teach bar, as each sentence the microphone recognises (origin `speech`; Azure AI Speech with a token from `POST /speech/token`, or the browser's recogniser when the API answers 503 or Azure Speech fails), or as a document uploaded to `POST /import/sentences`, whose stored sentences are taught one by one by `importRef`; the API parses every sentence. Theme and coverage writes are not persisted. A refusal from the API (403, 409 `channel_disabled`, or 503 for a change kind it does not serve yet) shows as the reference's toast. Dev builds send `X-Ontaix-User` only when `?user=<email>` is in the URL or `VITE_ONTAIX_DEV_USER` is set (the dev stack sets it); without either, a dev build signs in like a production build, which does not contain the header.

### Sign-In and Sessions

Against a real API the Studio reads `GET /auth/session` first (`src/auth/Gate.tsx`). A `401` shows the sign-in page (or, with the dev identity header, the Studio as the header user); a member session shows the Studio, or only the "Choose a new password" page while `mustChangePassword` is true; a super admin's session shows the platform portal (`src/platform`: Organizations, Platform audit log), and the Studio read-only inside a support session, with the header pill `Support · <organization> · read-only` and `End support` in `#adminAccount`. The session cookie is `HttpOnly`; the client keeps only its CSRF token (`src/api/session.ts`) and sends it as `X-CSRF-Token` on every POST, PUT, PATCH and DELETE. A `401` from any later call returns to the sign-in page with `Your session has ended. Sign in again.`; a `403 password_change_required` returns to the password page. Every screen text is ADR 0017 section 9's, built from the reference's own classes and tokens. The in-browser mock has no sessions, so in mock mode the Studio mounts directly and `#adminAccount` is not rendered.

Proposal text from the API (`html`) is passed through an allow-list sanitiser (`b`, `i`, `em`, `span.class`) before it is injected; every other string from the model is rendered as text.
