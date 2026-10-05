/**
 * Baselines of the compact teach bar in each of its states (the
 * canvas scenes capture it at rest). Each state is captured at 1440x900 and 1920x1080 in
 * light and dark, and at 390x844, and compared with a stored baseline under
 * tests/screenshots/baselines at 0.1 percent tolerance. Only the bottom of the page, where the
 * bar, the tools row and the open history sit, is captured.
 *
 * States: collapsed and idle; collapsed with a long caption; listening; processing with a queued
 * sentence; not understood with the sentence put back; open with the history and a long sentence;
 * live teaching off. Every run starts collapsed.
 *
 * `--update-snapshots` writes the baselines of the running platform.
 */
import { test, expect, type Page } from '../../apps/studio/test-support/playwright';
import { advance, fontsReady, openStudio, TOLERANCE, useTheme, VIEWPORTS, type Theme, type Viewport } from './harness';

/** The narrow viewport of the proposal's mobile layout. */
const PHONE: Viewport = { width: 390, height: 844 };
/** Height of the captured strip at the bottom of the page. */
const STRIP = 440;

const LONG_CAPTION =
  'Pump is a product · Plant produces Pump · Production line assembles Pump · Quality inspects every batch before it leaves the plant. Waiting for your approval on the right.';
const LONG_SENTENCE =
  'In quality, an inspection checks every batch of pumps before it leaves the plant, and each failed inspection opens a non-conformity that the quality engineer owns until it is closed.';
const HINT = 'Try "<subject> <action> <object>", "A is a B", or "A that … is a B". Start with "In quality, …" to choose the domain product.';

type StoreHandle = {
  caption(kicker: string, text: string): void;
  setSay(v: string): void;
  bump(): void;
  ui: { listening: boolean; processing: number; settings: Record<string, unknown> | null };
};

/** Runs `fn` in the page against the Studio's store, which the test build exposes. */
async function withStore<A>(page: Page, fn: (store: StoreHandle, arg: A) => void, arg?: A): Promise<void> {
  const store = await page.evaluateHandle(() => (window as unknown as { __ontaix: { store: StoreHandle } }).__ontaix.store);
  await store.evaluate(fn, arg as A);
}

interface State {
  name: string;
  drive: (page: Page) => Promise<void>;
}

const STATES: State[] = [
  { name: 'collapsed-idle', drive: async () => undefined },
  {
    name: 'collapsed-long-caption',
    drive: (page) => withStore(page, (store, text) => store.caption('Understood 4 statements', text), LONG_CAPTION),
  },
  {
    name: 'listening',
    drive: (page) =>
      withStore(
        page,
        (store, words) => {
          store.ui.listening = true;
          store.setSay(words);
        },
        'In sales, a customer places',
      ),
  },
  {
    name: 'processing',
    drive: (page) =>
      withStore(page, (store) => {
        store.caption('Understood 2 statements', 'Pump is a product · Plant produces Pump.');
        store.ui.processing = 2;
        store.bump();
      }),
  },
  {
    name: 'not-understood',
    drive: (page) =>
      withStore(
        page,
        (store, arg) => {
          store.caption('Not understood', arg.hint);
          store.setSay(arg.say);
        },
        { hint: HINT, say: 'purple elephants dance' },
      ),
  },
  {
    name: 'expanded',
    drive: async (page) => {
      await withStore(
        page,
        (store, arg) => {
          store.caption('Approved', 'Pump is now part of Production, version 3.');
          store.caption('Not understood', arg.hint);
          store.caption('Understood 2 statements', 'Pump is a product · Plant produces Pump. Waiting for your approval on the right.');
          store.setSay(arg.say);
        },
        { hint: HINT, say: LONG_SENTENCE },
      );
      await page.focus('#teachMore');
      await page.keyboard.press('Enter');
      await expect(page.locator('#teachMore')).toHaveAttribute('aria-expanded', 'true');
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    },
  },
  {
    name: 'live-teaching-off',
    drive: (page) =>
      withStore(page, (store) => {
        store.ui.settings = { ...(store.ui.settings || {}), liveTeaching: false };
        store.bump();
      }),
  },
];

const themes: Theme[] = ['light', 'dark'];
const only = process.env.ONTAIX_SCENE?.split(',');
const onlyTheme = process.env.ONTAIX_THEME;

for (const vp of [...VIEWPORTS, PHONE]) {
  for (const state of STATES) {
    if (only && !only.some((o) => state.name.includes(o))) continue;
    for (const theme of themes) {
      if (onlyTheme && onlyTheme !== theme) continue;
      const name = `teachbar-${state.name}-${theme}-${vp.width}x${vp.height}`;
      test(`${state.name} · ${theme} · ${vp.width}x${vp.height}`, async ({ browser }) => {
        const ctx = await browser.newContext({ viewport: vp });
        const page = await ctx.newPage();
        try {
          await openStudio(page);
          await useTheme(page, theme);
          await fontsReady(page);
          await advance(page, 500);
          await state.drive(page);
          // The caption typer, the status delay and the log's entrance finish before the capture.
          await advance(page, 5000);
          await expect(page).toHaveScreenshot(`${name}.png`, {
            clip: { x: 0, y: vp.height - STRIP, width: vp.width, height: STRIP },
            animations: 'disabled',
            caret: 'hide',
            maxDiffPixelRatio: TOLERANCE,
          });
        } finally {
          await ctx.close();
        }
      });
    }
  }
}
