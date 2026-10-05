/**
 * Drives the Studio under one seeded random source and one fake clock, so every run draws the
 * same numbers in the same frames, and compares each scene with its stored baseline under
 * tests/screenshots/baselines (one image per scene, theme, viewport and platform).
 */
import { expect, type Page } from '../../apps/studio/test-support/playwright';

/** Seed the Studio draws from; fixed so that a run is reproducible on every machine. */
export const SEED = 42;
/** Fake wall clock at page load. */
export const START_TIME = new Date('2026-09-28T09:00:00Z');
/** Fraction of pixels allowed to differ from the baseline. */
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

/** The localStorage key of the Studio's open teach bar; cleared so every run starts collapsed. */
export const TEACH_BAR_EXPANDED_KEY = 'ontaix.teachBar.expanded';

/** The baseline name of a scene: `{scene}-{theme}-{width}x{height}.png`, the platform added by the config. */
export const snapshotName = (scene: string, theme: Theme, vp: Viewport): string => `${scene}-${theme}-${vp.width}x${vp.height}.png`;

/**
 * Installs the fake clock and pauses it before navigation, so no frame runs until the test
 * advances time, and clears the remembered teach bar state.
 */
export async function prepare(page: Page): Promise<void> {
  await page.clock.install({ time: START_TIME });
  await page.clock.pauseAt(START_TIME);
  await page.addInitScript((key) => {
    try {
      localStorage.removeItem(key);
    } catch {
      // No storage: the teach bar starts collapsed anyway.
    }
  }, TEACH_BAR_EXPANDED_KEY);
}

/**
 * The fake clock accrues a few milliseconds of real time, different on every run, between its
 * install and its pause while the document is created. Everything the page does at load happens
 * inside that offset, and nothing there depends on time; from the first frame on, births and
 * clicks must land on identical ticks on every run. Advancing to the first frame boundary (tick
 * 16) removes the offset before any interaction.
 */
export async function alignClock(page: Page): Promise<void> {
  const ticks = await page.evaluate(() => performance.now());
  const toFrame = (16 - (Math.ceil(ticks) % 16)) % 16;
  if (toFrame) await page.clock.runFor(toFrame);
}

/** Opens the Studio on the in-browser mock with the fixed seed. */
export async function openStudio(page: Page): Promise<void> {
  await prepare(page);
  await page.goto(`/?seed=${SEED}&api=mock`);
  await page.waitForFunction(() => document.documentElement.dataset.ontaixReady === 'ready');
  await alignClock(page);
}

/** Waits for the UI typeface so the canvas and the DOM use the final glyphs. */
export async function fontsReady(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const weights = ['300', '400', '500', '600'];
    await Promise.all(weights.map((w) => document.fonts.load(`${w} 13px 'Hanken Grotesk Variable'`)));
    await document.fonts.load("400 12px 'IBM Plex Mono'");
    await document.fonts.ready;
  });
}

/**
 * Waits until every finite CSS animation and transition on the page has run to its end, then two
 * frames so the compositor shows that end state. For pages without a fake clock, where entrance
 * animations (`propin`, `fade`) run in real time: a capture with `animations: 'disabled'` jumps
 * a running animation to its end on the main thread, and Chromium sometimes keeps showing the
 * composited mid-way frame of an opacity and transform animation, the same frame in every
 * capture. An animation that finished on its own leaves no such frame. Infinite animations
 * (spinners) are left to the capture, which cancels them.
 */
export async function animationsSettled(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const finite = document.getAnimations().filter((a) => Number.isFinite(a.effect?.getComputedTiming().endTime ?? Infinity));
    await Promise.all(finite.map((a) => a.finished.catch(() => undefined)));
    await new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done())));
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

/** The Studio's caption sequence, bumped by every caption. */
async function captionSeq(page: Page): Promise<number> {
  return page.evaluate(() => (window as unknown as { __ontaix: { store: { ui: { caption: { seq: number } } } } }).__ontaix.store.ui.caption.seq);
}

/** Waits until the Studio has captioned the outcome of an action whose API calls resolve in microtasks. */
async function captioned(page: Page, before: number): Promise<void> {
  await page.waitForFunction(
    (seq) => (window as unknown as { __ontaix: { store: { ui: { caption: { seq: number } } } } }).__ontaix.store.ui.caption.seq > seq,
    before,
  );
}

const blur = (page: Page) => page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());

/** Teaches the active company one sentence typed into the teach bar. */
export async function teachText(page: Page, sentence: string): Promise<void> {
  const seq = await captionSeq(page);
  await page.fill('#say', sentence);
  await page.press('#say', 'Enter');
  await blur(page);
  await captioned(page, seq);
}

/**
 * Answers the Studio's whole-document job with `503`, as the e2e suite does, so an imported
 * document is read sentence by sentence. The mock API answers `fetch` in the page, so the refusal
 * wraps `window.fetch` there rather than a Playwright route.
 */
async function refuseWholeDocument(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as Window & { __ontaixRefuseWholeDocument?: boolean };
    if (w.__ontaixRefuseWholeDocument) return;
    w.__ontaixRefuseWholeDocument = true;
    const previous = window.fetch.bind(window);
    window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (!/\/api\/v1\/import\/[^/]+\/extraction$/.test(new URL(url, location.origin).pathname)) return previous(input, init);
      const problem = { title: 'Unavailable', status: 503, code: 'unavailable', detail: 'not in this scene' };
      return Promise.resolve(
        new Response(JSON.stringify(problem), { status: 503, headers: { 'content-type': 'application/problem+json' } }),
      );
    };
  });
}

/** Imports a text document through the file input and lets every sentence run. */
export async function importText(page: Page, name: string, text: string, ms = 2000): Promise<void> {
  await refuseWholeDocument(page);
  const before = await page.locator('#propList .prop').count();
  await page.setInputFiles('#importFile', { name, mimeType: 'text/plain', buffer: Buffer.from(text, 'utf-8') });
  // The file is read in real time; the first sentence is taught at once after the refused
  // whole-document read, so the clock stays put until then.
  const proposals = () => page.locator('#propList .prop').count();
  const started = Date.now();
  while ((await proposals()) <= before) {
    if (Date.now() - started > 30_000) throw new Error('the import proposed nothing within 30 s');
    await page.waitForTimeout(20);
  }
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
}

/**
 * Proposes a relation through the relationship box: cell `a` is dragged onto cell `b`, the action
 * is typed and Enter proposes. Across companies, `equivalent to` proposes an equivalence. The
 * drag reads the cells' screen positions from the Studio's store.
 */
export async function relate(page: Page, a: [string, string], b: [string, string], action: string): Promise<void> {
  const [from, to] = await page.evaluate(
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
}

/** Sentences that grow the home company one concept at a time, each from a concept already there. */
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
  await page.keyboard.press('s');
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
}

/**
 * Puts the page in a theme the way a user does: admin portal, theme button, close. Light is the
 * default, so a light scene changes nothing.
 */
export async function useTheme(page: Page, theme: Theme): Promise<void> {
  const current = await page.evaluate(() => document.documentElement.dataset.theme);
  if (current === theme) return;
  await page.keyboard.press('g');
  await page.click('#themeBtn');
  await page.keyboard.press('g');
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
}

export interface ShotOptions {
  animations?: 'disabled' | 'allow';
  caret?: 'hide' | 'initial';
  clip?: { x: number; y: number; width: number; height: number };
}

/** Compares the page with the scene's baseline at the tolerance; `--update-snapshots` writes the baseline. */
export async function expectScene(page: Page, scene: string, theme: Theme, vp: Viewport, options: ShotOptions = {}): Promise<void> {
  await expect(page).toHaveScreenshot(snapshotName(scene, theme, vp), { maxDiffPixelRatio: TOLERANCE, ...options });
}
