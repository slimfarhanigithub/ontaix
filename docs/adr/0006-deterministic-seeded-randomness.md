# ADR 0006: Deterministic Seeded Randomness In Test Mode

Status: Proposed. Pending owner approval at checkpoint 1.

## Context

The acceptance test compares screenshots of the Studio against the reference at 0.1 percent pixel tolerance. The reference uses `Math.random()` in several places: division angle noise (plus or minus 0.6 rad), link curve bend (`(seed - 0.5) * 0.3`), binding freshness (`2 min`, `4 min`, `11 min`, `1 h`), generic record counts (`800..9800`), discovery row counts (`200..90199`), conflict jitter, clash line jitter and near-zero repulsion nudges. Without control over these, no two renders match.

## Decision

Every random draw in the Studio and in the API goes through one injectable random source, never `Math.random()` or Python `random` directly.

- Studio: a `rng` module exports `next()` and `range(a, b)`. In normal mode it wraps `crypto.getRandomValues`. In test mode (`?seed=<n>` in the URL, or `VITE_ONTAIX_SEED` at build time) it is a mulberry32 generator seeded with that value. The renderer port replaces each `Math.random()` with `rng.next()` and nothing else changes.
- API: a `Randomness` dependency with the same two methods. In normal mode it wraps `secrets.SystemRandom`. When `ONTAIX_TEST_SEED` is set, it is `random.Random(seed)`. Freshness, generic record counts and discovery row counts are drawn from it.
- Seeds are per draw stream: the Studio derives the physics stream, the link seed stream and the caption stream from the base seed with fixed offsets so that adding a draw in one stream does not shift the others.
- Server-generated values that the canvas draws (freshness, record counts, `seed` of a relation) are stored on the row and returned by the API, so the client never re-rolls them. The relation `seed` column exists for this reason.
- The reference file itself is rendered for the baseline with the same seed injected: the Playwright fixture overrides `Math.random` in the reference page with the identical mulberry32 sequence before the page script runs, and freezes `Date.now` and `performance.now` to a scripted clock so that `bornAt` stamps and animation frames align. Both sides therefore draw the same numbers in the same order.
- Time is injected the same way: the Studio reads the clock through one `clock` module that the test harness advances frame by frame at 60 frames per second; the API stamps `bornAt` from a `Clock` dependency that the test fixture freezes.

## Consequences

- Screenshots are reproducible on every machine and in CI.
- Production keeps real randomness and real time; the seed switch is off by default.
- Any new random or time dependence must go through the two modules, which the QA agent enforces with a lint rule that forbids `Math.random`, `Date.now` and `performance.now` outside them.
