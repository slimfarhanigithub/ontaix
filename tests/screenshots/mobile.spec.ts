/**
 * Screenshot regression of the Studio on a phone: 390x844, a touch screen (coarse pointer), the
 * same seed and fake clock as the canvas scenes, compared with its stored baseline at 0.1 percent
 * tolerance. Under 900 px the changes panel is a full-screen sheet opened from `Show changes`, the
 * tool row and the domains card stay on the canvas, and every control a finger aims at offers at
 * least 40 px.
 *
 * Scenes: empty canvas; pending proposals; the changes sheet open; the first model approved
 * through the sheet; the domains card open; the drawer of a cell; the admin portal's Overview.
 *
 * `--update-snapshots` writes the baselines of the running platform.
 */
import { test, type Page } from '../../apps/studio/test-support/playwright';
import { advance, approveAll, expectScene, fontsReady, openStudio, teachFirstModel, type Viewport } from './harness';

/** The phone of the UI contract's teach bar baselines. */
const PHONE: Viewport = { width: 390, height: 844 };

interface PhoneScene {
  name: string;
  play: (page: Page) => Promise<void>;
}

/** Teaches the first model, approves it from the changes sheet and closes the sheet. */
async function approvedModel(page: Page): Promise<void> {
  await teachFirstModel(page);
  await advance(page, 1100);
  await page.tap('#panelShow');
  await approveAll(page);
  await page.tap('#panelHide');
  await advance(page, 4000);
}

const scenes: PhoneScene[] = [
  {
    name: 'empty-canvas',
    play: async (page) => {
      await fontsReady(page);
      await advance(page, 5000);
    },
  },
  {
    name: 'pending-proposals',
    play: async (page) => {
      await teachFirstModel(page);
      await advance(page, 5000);
    },
  },
  {
    name: 'changes-sheet',
    play: async (page) => {
      await teachFirstModel(page);
      await advance(page, 1100);
      await page.tap('#panelShow');
      await advance(page, 1000);
    },
  },
  {
    name: 'first-model-approved',
    play: approvedModel,
  },
  {
    name: 'domains-open',
    play: async (page) => {
      await approvedModel(page);
      await page.tap('#domainsToggle');
      await advance(page, 1000);
    },
  },
  {
    name: 'drawer',
    play: async (page) => {
      await approvedModel(page);
      await page.evaluate(() => {
        type N = { label: string };
        const store = (window as unknown as { __ontaix: { store: { s: { nodes: N[] }; openDrawer(n: N): void } } }).__ontaix.store;
        const n = store.s.nodes.find((x) => x.label === 'Sales order');
        if (!n) throw new Error('no Sales order cell');
        store.openDrawer(n);
      });
      await advance(page, 1000);
    },
  },
  {
    name: 'admin-overview',
    play: async (page) => {
      await fontsReady(page);
      await advance(page, 500);
      await page.tap('#adminOpen');
      await advance(page, 1500);
    },
  },
];

const only = process.env.ONTAIX_SCENE?.split(',');

for (const scene of scenes) {
  if (only && !only.some((o) => scene.name.includes(o))) continue;
  const name = `phone-${scene.name}`;
  test(`${name} · ${PHONE.width}x${PHONE.height}`, async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: PHONE, isMobile: true, hasTouch: true, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    try {
      await openStudio(page);
      await scene.play(page);
      await expectScene(page, name, PHONE, { animations: 'disabled', caret: 'hide' });
    } finally {
      await ctx.close();
    }
  });
}
