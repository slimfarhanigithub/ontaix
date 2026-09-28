/**
 * The single random source of the Studio. Every draw the canvas makes goes through `random()`.
 *
 * Normal mode wraps `crypto.getRandomValues`. Test mode (`?seed=<n>` in the URL or
 * `VITE_ONTAIX_SEED` at build time) is a mulberry32 generator seeded with that value, so a
 * screenshot run draws the same numbers as the reference page whose `Math.random` the harness
 * replaces with the identical generator.
 *
 * One stream, not several: the reference has one `Math.random`, so the only way the two pages
 * draw the same sequence is to consume one stream in the same order.
 */

export function mulberry32(seed: number): () => number {
  let a = seed | 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function cryptoRandom(): number {
  const buf = new Uint32Array(1);
  crypto.getRandomValues(buf);
  return buf[0] / 4294967296;
}

let source: () => number = cryptoRandom;
let activeSeed: number | null = null;
let trace: ((t: number, v: number) => void) | null = null;

/** Switch to a seeded stream (test mode) or back to the cryptographic source with `null`. */
export function seedRandom(seed: number | null): void {
  activeSeed = seed;
  const base = seed === null ? cryptoRandom : mulberry32(seed);
  source = () => {
    const v = base();
    if (trace) trace(performance.now(), v);
    return v;
  };
}

/** Records every draw with its time; the screenshot harness compares the stream with the reference's. */
export function traceDraws(sink: ((t: number, v: number) => void) | null): void {
  trace = sink;
}

/** The seed in force, or `null` in normal mode. */
export function currentSeed(): number | null {
  return activeSeed;
}

/** A draw in [0, 1), like `Math.random()`. */
export const random = (): number => source();

/** A draw in [a, b). */
export const range = (a: number, b: number): number => a + (b - a) * random();

/** Reads `?seed=<n>` from a URL search string, falling back to the build-time seed. */
export function seedFromLocation(search: string, buildSeed: string | undefined): number | null {
  const fromUrl = new URLSearchParams(search).get('seed');
  const raw = fromUrl ?? buildSeed;
  if (raw === undefined || raw === null || raw === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}
