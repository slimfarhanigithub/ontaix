/**
 * Renders the reference file and the Studio side by side under one seeded random source and
 * one fake clock, so that both pages draw the same numbers in the same frames, and compares the
 * two screenshots pixel by pixel.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { mulberry32 } from '../../apps/studio/src/runtime/mulberry32';
import { expect, pixelmatch, PNG, type Page, type TestInfo } from '../../apps/studio/test-support/playwright';

const here = dirname(fileURLToPath(import.meta.url));
export const REFERENCE_URL = pathToFileURL(resolve(here, '../../reference/ontaix-studio-reference.html')).href;
export const OUTPUT_DIR = resolve(here, 'output');

/** Seed both pages draw from; fixed so that a run is reproducible on every machine. */
export const SEED = 42;
/** Fake wall clock at page load. */
export const START_TIME = new Date('2026-09-28T09:00:00Z');
/** Fraction of pixels allowed to differ. */
export const TOLERANCE = 0.001;

export type Theme = 'dark' | 'light';

export interface Viewport {
  width: number;
  height: number;
}

/** The two viewports the UI contract names. */
export const VIEWPORTS: Viewport[] = [
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
];

/**
 * Installs the fake clock and pauses it before navigation, so no frame runs until the test
 * advances time. The reference also gets `Math.random` replaced with the Studio's generator.
 */
export async function prepare(page: Page, opts: { seedMathRandom: boolean }): Promise<void> {
  await page.clock.install({ time: START_TIME });
  await page.clock.pauseAt(START_TIME);
  if (opts.seedMathRandom) {
    await page.addInitScript(
      `(() => { const g = (${mulberry32.toString()})(${SEED}); const draws = []; window.__ontaixDraws = draws; Math.random = () => { const v = g(); draws.push([performance.now(), v]); return v; }; })();`,
    );
  }
}

/**
 * The fake clock accrues a few milliseconds of real time, different on every run, between its
 * install and its pause while the document is created. Everything the page does at load happens
 * inside that offset, and nothing there depends on time; from the first frame on, births and
 * clicks must land on identical ticks on both pages. Advancing each page to the first frame
 * boundary (tick 16) removes the offset before any interaction.
 */
export async function alignClock(page: Page): Promise<void> {
  const ticks = await page.evaluate(() => performance.now());
  const toFrame = (16 - (Math.ceil(ticks) % 16)) % 16;
  if (toFrame) await page.clock.runFor(toFrame);
}

export async function openReference(page: Page): Promise<void> {
  await prepare(page, { seedMathRandom: true });
  await page.goto(REFERENCE_URL);
  await page.waitForSelector('canvas#brain');
  await alignClock(page);
}

export async function openStudio(page: Page): Promise<void> {
  await prepare(page, { seedMathRandom: false });
  await page.goto(`/?seed=${SEED}&api=mock`);
  await page.waitForFunction(() => document.documentElement.dataset.ontaixReady === 'ready');
  await alignClock(page);
}

/** Waits for Sora so the canvas and the DOM use the same glyphs on both pages. */
export async function fontsReady(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const weights = ['300', '400', '500', '600'];
    await Promise.all(weights.map((w) => document.fonts.load(`${w} 13px Sora`)));
    await document.fonts.ready;
  });
}

/** Advances the fake clock in steps so timers and animation frames interleave as in real time. */
export async function advance(page: Page, ms: number, stepMs = 250): Promise<void> {
  let left = ms;
  while (left > 0) {
    const step = Math.min(stepMs, left);
    await page.clock.runFor(step);
    left -= step;
  }
}

/** Switches the page to light mode the way a user does: admin portal, theme button, close. */
export async function switchToLight(page: Page): Promise<void> {
  await page.keyboard.press('g');
  await page.click('#themeBtn');
  await page.keyboard.press('g');
}

export interface Comparison {
  diffRatio: number;
  diffPixels: number;
  total: number;
}

function decode(buf: Buffer): PNG {
  return PNG.sync.read(buf);
}

/**
 * Compares two screenshots pixel for pixel (no colour threshold, anti-aliased pixels counted),
 * writes the images and the diff, and returns the differing fraction.
 */
export function compare(scene: string, theme: Theme, vp: Viewport, reference: Buffer, studio: Buffer): Comparison {
  const a = decode(reference),
    b = decode(studio);
  expect(a.width, 'screenshot widths').toBe(b.width);
  expect(a.height, 'screenshot heights').toBe(b.height);
  const diff = new PNG({ width: a.width, height: a.height });
  const diffPixels = pixelmatch(a.data, b.data, diff.data, a.width, a.height, { threshold: 0, includeAA: true });
  const total = a.width * a.height;
  const dir = resolve(OUTPUT_DIR, `${scene}-${theme}-${vp.width}x${vp.height}`);
  mkdirSync(dir, { recursive: true });
  writeFileSync(resolve(dir, 'reference.png'), reference);
  writeFileSync(resolve(dir, 'studio.png'), studio);
  writeFileSync(resolve(dir, 'diff.png'), PNG.sync.write(diff));
  return { diffRatio: diffPixels / total, diffPixels, total };
}

export function report(info: TestInfo, scene: string, theme: Theme, vp: Viewport, c: Comparison): void {
  const pct = (c.diffRatio * 100).toFixed(4);
  const line = `${scene} ${theme} ${vp.width}x${vp.height}: ${pct} % of pixels differ (${c.diffPixels} of ${c.total})`;
  console.log(line);
  info.annotations.push({ type: 'diff', description: line });
}

type Draw = [number, number];

/** Every random draw of a page with its clock time: the reference logs them from its patched `Math.random`, the Studio from its `rng` in test mode. */
export async function drawLog(page: Page, studio: boolean): Promise<Draw[]> {
  return page.evaluate((isStudio) => {
    const w = window as unknown as { __ontaixDraws?: Draw[]; __ontaix?: { draws: Draw[] } };
    return isStudio ? (w.__ontaix?.draws ?? []) : (w.__ontaixDraws ?? []);
  }, studio);
}

/** Where the two draw streams part, for the failure message: same values at the same times means the physics ran identically. */
export async function drawDivergence(ref: Page, studio: Page): Promise<string> {
  const a = await drawLog(ref, false),
    b = await drawLog(studio, true);
  // Draws made while the document loads (before the first frame) carry the load offset; their times are not compared.
  const same = (x: Draw, y: Draw) => x[1] === y[1] && (x[0] < 16 ? y[0] < 16 : x[0] === y[0]);
  let i = 0;
  while (i < a.length && i < b.length && same(a[i], b[i])) i++;
  if (i === a.length && i === b.length) return `draw streams identical (${a.length} draws)`;
  return `draw streams differ at #${i}: reference ${JSON.stringify(a.slice(i, i + 3))} vs studio ${JSON.stringify(b.slice(i, i + 3))} (${a.length} vs ${b.length} draws)`;
}
