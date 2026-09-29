/**
 * Renders the reference file and the Studio side by side under one seeded random source and
 * one fake clock, so that both pages draw the same numbers in the same frames, and compares the
 * two screenshots pixel by pixel.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { mulberry32 } from '../../apps/studio/src/runtime/mulberry32';
import { expect, pixelmatch, PNG, type Page, type TestInfo } from '../../apps/studio/test-support/playwright';

const here = dirname(fileURLToPath(import.meta.url));
export const REFERENCE_URL = pathToFileURL(resolve(here, '../../reference/ontaix-studio-reference.html')).href;
export const OUTPUT_DIR = resolve(here, 'output');
/** Sora as Google Fonts serves it (CSS and woff2 files), kept in the repository so no run depends on the network. */
export const FONTS_DIR = resolve(here, 'fonts');

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
 * The story-only elements of the reference, hidden in both pages with `display: none` so the
 * surrounding layout closes up as it does in a Studio that never renders them: the scene counter
 * and scene name (the admin button beside them stays), the Next button and Finalise all.
 */
const STORY_ONLY_CSS = '#sceneNum,#sceneName,#next,#finalise{display:none!important}';
/**
 * Owner additions absent from the reference, hidden in both pages with `display: none`: the
 * drawer's Expand and Delete buttons and the changes panel's `Approve branch` button. The
 * reference has no such elements, so the rule changes nothing there; in the Studio the drawer's
 * other actions and each proposal's row lay out as the reference's.
 */
const OWNER_ADDITIONS_CSS = '#drExpand,#drDelete,.prop .act .branch{display:none!important}';
/**
 * The import mode pill, an owner addition shown in every scene: the Studio's `#imMode` at its
 * default, added to the reference after `#importFile` before its first layout, so both tool rows
 * hold it from the start and every other pixel still compares against the reference.
 */
export const IMPORT_MODE_PILL =
  '<button type="button" id="imMode" title="How the next imported document is read" aria-pressed="false"><svg viewBox="0 0 16 16"><path d="M3 4h10M3 8h10M3 12h6"></path></svg>Sentences</button>';
const ADD_IMPORT_MODE_PILL = `document.addEventListener('DOMContentLoaded', () => {
  if (!document.getElementById('imMode')) document.getElementById('importFile')?.insertAdjacentHTML('afterend', ${JSON.stringify(IMPORT_MODE_PILL)});
}, { once: true });`;
/** The caption, hidden while the reference still shows the story's opening caption. */
const OPENING_CAPTION_CSS = '.caption{visibility:hidden!important}';
/** The teach placeholder, made transparent in one-company scenes with live teaching on, where the reference shows story text. */
const PLACEHOLDER_CSS = '#say::placeholder{color:transparent!important}';

/** Adds the acceptance stylesheets to a page as soon as its document exists. */
const ACCEPTANCE_STYLES = `(() => {
  const add = () => {
    for (const [id, css] of ${JSON.stringify([
      ['ontaix-story-only', STORY_ONLY_CSS],
      ['ontaix-owner-additions', OWNER_ADDITIONS_CSS],
      ['ontaix-opening-caption', OPENING_CAPTION_CSS],
    ])}) {
      if (document.getElementById(id)) continue;
      const style = document.createElement('style');
      style.id = id;
      style.textContent = css;
      document.head.appendChild(style);
    }
  };
  if (document.head) add();
  else document.addEventListener('DOMContentLoaded', add, { once: true });
})();`;

/**
 * Removes the two story fragments of `.hint`: the first `kbd` (`Space`) with the text node after
 * it, the last `kbd` (`R`) with the text node after it, and sets the text node after `<kbd>F</kbd>`
 * to exactly ` full screen`. The Studio renders the hint in that form already, so nothing changes there.
 */
function stripHintStory(): void {
  const hint = document.querySelector('.hint');
  if (!hint) return;
  const kbds = hint.querySelectorAll('kbd');
  const drop = (k: Element | undefined, text: string) => {
    if (!k || k.textContent !== text) return;
    if (k.nextSibling && k.nextSibling.nodeType === Node.TEXT_NODE) k.nextSibling.remove();
    k.remove();
  };
  drop(kbds[0], 'Space');
  drop(kbds[kbds.length - 1], 'R');
  const f = Array.from(hint.querySelectorAll('kbd')).find((k) => k.textContent === 'F');
  if (f && f.nextSibling && f.nextSibling.nodeType === Node.TEXT_NODE) f.nextSibling.textContent = ' full screen';
}

/** Shows the caption once the first teach, import, company or decision has replaced the reference's opening caption. */
export async function revealCaption(page: Page): Promise<void> {
  await page.evaluate(() => document.getElementById('ontaix-opening-caption')?.remove());
}

/**
 * Brings both pages to the compared form just before the screenshot: the reference's import mode
 * pill checked equal to the Studio's and shown or hidden with its Import button, the hint without its story fragments
 * (asserted equal as text), and the teach placeholder made transparent in both pages when the
 * reference has one company and live teaching on, where it still shows story text.
 */
export async function beforeScreenshot(ref: Page, studio: Page): Promise<void> {
  const pill = await studio.evaluate(() => {
    const copy = document.getElementById('imMode')?.cloneNode(true) as HTMLElement | undefined;
    copy?.removeAttribute('style');
    return copy?.outerHTML ?? '';
  });
  expect(pill, 'the reference holds the same import mode pill as the Studio').toBe(IMPORT_MODE_PILL);
  await ref.evaluate(() => {
    const added = document.getElementById('imMode');
    const importBtn = document.getElementById('importBtn');
    if (added && importBtn) added.style.display = importBtn.style.display;
  });
  await ref.evaluate(stripHintStory);
  await studio.evaluate(stripHintStory);
  const hints = await Promise.all([ref, studio].map((p) => p.evaluate(() => document.querySelector('.hint')?.textContent ?? '')));
  expect(hints[1], '.hint text of the Studio equals the reference without its story fragments').toBe(hints[0]);
  const storyPlaceholder = await ref.evaluate(() => {
    const say = document.getElementById('say') as HTMLInputElement | null;
    const companies = document.querySelectorAll('#companySel option').length;
    return !!say && companies < 2 && say.placeholder !== 'Live teaching is disabled in the admin portal';
  });
  if (!storyPlaceholder) return;
  for (const page of [ref, studio])
    await page.evaluate((css) => {
      if (document.getElementById('ontaix-placeholder')) return;
      const style = document.createElement('style');
      style.id = 'ontaix-placeholder';
      style.textContent = css;
      document.head.appendChild(style);
    }, PLACEHOLDER_CSS);
}

/**
 * Installs the fake clock and pauses it before navigation, so no frame runs until the test
 * advances time. The reference also gets `Math.random` replaced with the Studio's generator.
 */
export async function prepare(page: Page, opts: { seedMathRandom: boolean }): Promise<void> {
  await serveFontsLocally(page);
  await page.addInitScript(ACCEPTANCE_STYLES);
  await page.clock.install({ time: START_TIME });
  await page.clock.pauseAt(START_TIME);
  if (opts.seedMathRandom) {
    await page.addInitScript(
      `(() => { const g = (${mulberry32.toString()})(${SEED}); const draws = []; window.__ontaixDraws = draws; Math.random = () => { const v = g(); draws.push([performance.now(), v]); return v; }; })();`,
    );
  }
}

/**
 * Answers both pages' Google Fonts requests from tests/screenshots/fonts: the stylesheet for
 * fonts.googleapis.com and the woff2 files for fonts.gstatic.com, by file name. A file that is
 * not kept locally fails the request instead of reaching the network.
 */
export async function serveFontsLocally(page: Page): Promise<void> {
  const cors = { 'access-control-allow-origin': '*' };
  await page.route(/^https:\/\/fonts\.googleapis\.com\//, (route) =>
    route.fulfill({ status: 200, contentType: 'text/css; charset=utf-8', headers: cors, body: readFileSync(resolve(FONTS_DIR, 'sora.css')) }),
  );
  await page.route(/^https:\/\/fonts\.gstatic\.com\//, (route) => {
    const file = resolve(FONTS_DIR, basename(new URL(route.request().url()).pathname));
    if (!existsSync(file)) return route.fulfill({ status: 404, headers: cors, body: '' });
    return route.fulfill({ status: 200, contentType: 'font/woff2', headers: cors, body: readFileSync(file) });
  });
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
  await page.addInitScript(ADD_IMPORT_MODE_PILL);
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

/** The two pages of one comparison, driven in lockstep through the same user actions. */
export interface Pair {
  ref: Page;
  studio: Page;
}

/** Runs one drive step on the reference, then on the Studio. */
export async function both(pair: Pair, step: (page: Page) => Promise<void>): Promise<void> {
  await step(pair.ref);
  await step(pair.studio);
}

async function isStudio(page: Page): Promise<boolean> {
  return page.evaluate(() => '__ontaix' in window);
}

/** The Studio's caption sequence, bumped by every caption; the reference answers 0. */
async function captionSeq(page: Page): Promise<number> {
  return page.evaluate(() => (window as unknown as { __ontaix?: { store: { ui: { caption: { seq: number } } } } }).__ontaix?.store.ui.caption.seq ?? 0);
}

/** Waits until the Studio has captioned the outcome of an action whose API calls resolve in microtasks. */
async function captioned(page: Page, before: number): Promise<void> {
  if (!(await isStudio(page))) return;
  await page.waitForFunction(
    (seq) => (window as unknown as { __ontaix: { store: { ui: { caption: { seq: number } } } } }).__ontaix.store.ui.caption.seq > seq,
    before,
  );
}

const blur = (page: Page) => page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());

/**
 * Teaches the active company one sentence typed into the teach bar. The sentences never name what
 * the reference's next story scene listens for, so the reference reads them exactly as its import
 * path (`teach(sentence, true)`) does; the Studio sends them as `text`.
 */
export async function teachText(page: Page, sentence: string): Promise<void> {
  const seq = await captionSeq(page);
  const scene = () => page.evaluate(() => document.getElementById('sceneNum')?.textContent ?? null);
  const sceneBefore = await scene();
  await page.fill('#say', sentence);
  await page.press('#say', 'Enter');
  await blur(page);
  await captioned(page, seq);
  // The reference's scene counter stays put: the sentence was parsed, not played as a story scene.
  expect(await scene(), `"${sentence}" was taken by the reference's story instead of the parser`).toBe(sceneBefore);
  await revealCaption(page);
}

/** Imports a text document through the file input, the same user action on both pages, and lets every sentence run. */
export async function importText(page: Page, name: string, text: string, ms = 2000): Promise<void> {
  const before = await page.locator('#propList .prop').count();
  await page.setInputFiles('#importFile', { name, mimeType: 'text/plain', buffer: Buffer.from(text, 'utf-8') });
  // The file is read in real time on both pages; the first sentence is taught at once after that.
  await page.waitForFunction((n) => document.querySelectorAll('#propList .prop').length > n, before);
  await revealCaption(page);
  // Sentences are taught one clock tick apart; the clock advances until the import has finished.
  const finished = () => page.evaluate(() => /^Import (finished|failed)/.test(document.getElementById('captionKicker')?.textContent || ''));
  let spent = 0;
  while (!(await finished())) {
    if (spent >= 30_000) throw new Error('the import did not finish within 30 s of page time');
    await advance(page, 50, 50);
    spent += 50;
  }
  if (spent < ms) await advance(page, ms - spent);
}

/** Adds a company through the add-company dialog, starting with its starter vocabulary. */
export async function addCompanyWithStarter(page: Page, name: string, sub: string): Promise<void> {
  await page.click('#addCo');
  await advance(page, 300);
  await page.fill('#acName', name);
  await page.fill('#acSub', sub);
  const seq = await captionSeq(page);
  await page.click('.dlg .df .btn.primary');
  await blur(page);
  await captioned(page, seq);
  await revealCaption(page);
}

/**
 * Proposes a relation through the relationship box: cell `a` is dragged onto cell `b`, the action
 * is typed and Enter proposes. Across companies, `equivalent to` proposes an equivalence. Both
 * pages hold the same cells at the same places, so the drag reads them from the Studio's store.
 */
export async function relate(pair: Pair, a: [string, string], b: [string, string], action: string): Promise<void> {
  const [from, to] = await pair.studio.evaluate(
    ({ a, b }) => {
      type N = { label: string; x: number; y: number; company: { name: string } | null };
      const { store } = (
        window as unknown as {
          __ontaix: { store: { s: { nodes: N[]; cam: { x: number; y: number; s: number } }; renderer: { v: { W: number; H: number } } } };
        }
      ).__ontaix;
      const { s, renderer } = store;
      const panel = renderer.v.W > 900 && !document.body.classList.contains('panel-off') ? 320 : 0;
      const screen = ([label, company]: [string, string]): [number, number] => {
        const n = s.nodes.find((x) => x.label === label && x.company?.name === company);
        if (!n) throw new Error(`no cell ${label} in ${company}`);
        return [(n.x - s.cam.x) * s.cam.s + (renderer.v.W - panel) / 2, (n.y - s.cam.y) * s.cam.s + renderer.v.H / 2];
      };
      return [screen(a), screen(b)];
    },
    { a, b },
  );
  await both(pair, async (page) => {
    await page.mouse.move(from[0], from[1]);
    await page.mouse.down();
    await page.mouse.move(to[0], to[1], { steps: 6 });
    await page.mouse.up();
    await advance(page, 300);
    const seq = await captionSeq(page);
    await page.fill('#lbAction', action);
    await page.press('#lbAction', 'Enter');
    await blur(page);
    await captioned(page, seq);
    await revealCaption(page);
  });
}

/**
 * Sentences that grow the home company one concept at a time, each from a concept already there.
 * None names a plant, production line, machine or shift, the words the reference's first story
 * scene listens for.
 */
export const FIRST_MODEL = [
  'In sales, Northwind Industries serves customers.',
  'In sales, a customer places sales orders.',
  'In sales, a sales order contains products.',
  'In logistics, a sales order is fulfilled by deliveries.',
];

/** Fonts, animations off, then the first model taught sentence by sentence. */
export async function teachFirstModel(page: Page): Promise<void> {
  await fontsReady(page);
  await advance(page, 500);
  await page.click('#skip');
  for (const sentence of FIRST_MODEL) {
    await teachText(page, sentence);
    await advance(page, 400);
  }
}

/** Approves every ready proposal from the changes panel. */
export async function approveAll(page: Page): Promise<void> {
  const seq = await captionSeq(page);
  await page.click('#approveAll');
  await captioned(page, seq);
  await revealCaption(page);
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
