# Ontaix Studio

React 19 + TypeScript + Vite, tested with vitest. The Studio must be identical to `reference/ontaix-studio-reference.html`; read `docs/ui-contract.md` before changing anything here. The canvas renderer is ported verbatim from the reference in a later wave. Fonts are loaded per the reference when that port lands, not before.

## Layout

```text
index.html           Vite entry document
src/
  main.tsx           mounts <App /> into #root
  App.tsx            placeholder shell rendering "Ontaix Studio"
  App.test.tsx       smoke test
  test-setup.ts      jest-dom matchers for vitest
```

## Run Locally

From the repository root:

```bash
pnpm install
pnpm --filter studio dev
pnpm --filter studio test
pnpm --filter studio build
```
