/**
 * The single random source of the Studio. Every draw the canvas makes goes through `random()`.
 *
 * Normal mode wraps `crypto.getRandomValues`. Test mode (dev builds or `VITE_ONTAIX_TEST_HOOKS`)
 * swaps in a seeded generator so a screenshot run draws the same numbers as the reference page,
 * whose `Math.random` the harness replaces with the identical generator.
 *
 * One stream, not several: the reference has one `Math.random`, so the only way the two pages
 * draw the same sequence is to consume one stream in the same order.
 */

function cryptoRandom(): number {
  const buf = new Uint32Array(1);
  crypto.getRandomValues(buf);
  return buf[0] / 4294967296;
}

let source: () => number = cryptoRandom;
let trace: ((t: number, v: number) => void) | null = null;

/** Replaces the source (a seeded generator in test mode); `null` restores the cryptographic one. */
export function setSource(fn: (() => number) | null): void {
  source = fn ?? cryptoRandom;
}

/** Records every draw with its time; the screenshot harness compares the stream with the reference's. */
export function traceDraws(sink: ((t: number, v: number) => void) | null): void {
  trace = sink;
}

/** A draw in [0, 1), like `Math.random()`. */
export const random = (): number => {
  const v = source();
  if (trace) trace(performance.now(), v);
  return v;
};

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
