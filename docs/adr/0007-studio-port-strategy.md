# ADR 0007: Studio Port Strategy

Status: Proposed. Pending owner approval at checkpoint 1.

## Context

`reference/ontaix-studio-reference.html` is a single 1101-line file: CSS, markup and about 850 lines of script that mix the canvas renderer, the physics, the story, the parser, the admin portal and persistence. The Studio must be pixel-identical to it, must run against the real API, and is built by two agents (Studio front end, Admin portal front end) starting on day 2, before the API exists.

## Decision

The Studio is React 19 + TypeScript + Vite. The renderer is ported verbatim; the shell and the admin portal are rebuilt as components that produce the same DOM and the same CSS.

```mermaid
flowchart TB
  subgraph verbatim[Verbatim modules · constants never change]
    physics[canvas/physics.ts]
    draw[canvas/draw.ts]
    division[canvas/division.ts]
    hulls[canvas/regions.ts]
    links[canvas/links.ts]
    labels[canvas/labels.ts]
    arrange[canvas/arrange.ts]
    focus[canvas/focus.ts]
    lineage[canvas/lineage.ts]
    parser[nl/parser.ts]
    suggest[nl/suggest.ts]
  end
  subgraph rebuilt[Rebuilt · same DOM, same CSS]
    shell[Shell · header, bar, tools, caption, panel, drawer, boxes]
    admin[Admin portal · 15 pages, dialogs, lists, wizard]
  end
  subgraph data[Data layer]
    store[Scene store · nodes, links, proposals, settings]
    client[API client · generated from contracts/openapi.yaml]
    mock[Mock API · fixtures from the reference constants]
    ws[WebSocket client]
  end
  verbatim --> store
  rebuilt --> store
  store --> client
  store --> ws
  client -.->|wave 2| mock
```

Rules:

- Verbatim modules copy the reference functions line for line into TypeScript with types added and `Math.random`, `Date.now` and `performance.now` replaced by the injected `rng` and `clock` (ADR 0006). Renaming a local variable or splitting a function is allowed; changing a constant, an easing, a colour, a threshold or an order of operations is a bug. Each module header names the reference line range it was ported from.
- The dead `ghosts` / `drawGhosts` code and the unused `VERBS` array are not ported.
- CSS is copied from the reference into one stylesheet with the same selectors; the design tokens in `contracts/design-tokens.json` generate the `:root` custom properties and the canvas theme object, so a token change lands in both places at once.
- The scene store holds the same arrays the reference has (`nodes`, `links`, `proposals`, `companies`, settings) so that the verbatim modules run unchanged. `GET /api/v1/scene` fills it; WebSocket events update it; every user action calls the API and applies the returned artefacts.
- Wave 2 runs against a mock API in the browser (MSW) that implements `contracts/openapi.yaml` over an in-memory store seeded from the reference constants (`DOMAIN_TEMPLATES`, `SEED`, `RECORDS`, `ATTR`, `CATALOG`, `DISCOVER`, the 180 users, the 2400 agents). The mock is the same code path the QA scene tests use, and the real API replaces it by changing one base URL in wave 3.
- The scripted story (scenes, Next, Finalise all, R restart) is a demo layer behind the tenant feature flag `demoStory`, on in dev. When off, the header shows no scene counter and the Next button is hidden; the rest of the shell is unchanged.
- Screenshot regression runs from day 4: each scene is rendered from the reference file and from the Studio with the same seed and clock, at 1440 by 900 and 1920 by 1080, dark and light.

## Consequences

- Two agents work in parallel: canvas and shell in `apps/studio/src`, admin portal in `apps/studio/src/admin`, sharing the store and the generated client.
- The canvas is testable in isolation with the mock API before the backend exists.
- Any visible difference traces to either a non-verbatim edit or a data difference, never to both at once.
