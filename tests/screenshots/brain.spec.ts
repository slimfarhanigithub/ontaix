/**
 * Screenshot regression of the demo brain built on a first model, same seed and fake clock as the
 * canvas scenes, compared with its stored baseline at 0.1 percent tolerance.
 *
 * Scenes, each a moment of the demo's own plan: the new concepts being fed by the sources close up
 * (1.8 s after the first one buds); the brain growing, fed by the sources (3 s into the growth);
 * the wave of light running through the grown brain (0.4 s after it has grown); the grown brain
 * glowing, its sources around it (2.5 s after it has grown). The first two run at 1440x900 and on
 * a phone (390x844, touch); the last two at 1440x900.
 *
 * The first model is taught with Skip animation on, as every canvas scene is; the scene turns it
 * off with `S` before starting the demo, so the demo plays.
 *
 * `--update-snapshots` writes the baselines of the running platform.
 */
import { test, type Page } from '../../apps/studio/test-support/playwright';
import { advance, approveAll, expectScene, openStudio, teachFirstModel, type Viewport } from './harness';

const DESKTOP: Viewport = { width: 1440, height: 900 };
const PHONE: Viewport = { width: 390, height: 844 };

interface Plan {
  mapping: number;
  feeding: number;
  finale: number;
  grown: number;
}

interface BrainScene {
  name: string;
  /** Seconds after the demo starts at which the frame is taken. */
  at: (p: Plan) => number;
  viewports: Viewport[];
}

const scenes: BrainScene[] = [
  { name: 'brain-mapping', at: (p) => p.mapping, viewports: [DESKTOP, PHONE] },
  { name: 'brain-feeding', at: (p) => p.feeding, viewports: [DESKTOP, PHONE] },
  { name: 'brain-finale', at: (p) => p.finale, viewports: [DESKTOP] },
  { name: 'brain-grown', at: (p) => p.grown, viewports: [DESKTOP] },
];

/** Teaches and approves the first model, turns animations back on and starts the demo; answers its plan. */
async function startDemo(page: Page, phone: boolean): Promise<Plan> {
  await teachFirstModel(page);
  await advance(page, 1100);
  if (phone) await page.tap('#panelShow');
  await approveAll(page);
  if (phone) await page.tap('#panelHide');
  await advance(page, 4000);
  await page.keyboard.press('s');
  if (phone) await page.tap('#brainDemo');
  else await page.click('#brainDemo');
  return page.evaluate(() => {
    type Demo = { stories: number; growAt: number; duration: number; cells: { born: number; story: { source: boolean } | null }[] };
    const d = (window as unknown as { __ontaix: { store: { s: { brain: Demo } } } }).__ontaix.store.s.brain;
    const fed = d.cells.slice(0, d.stories).filter((c) => !c.story?.source);
    const firstFed = Math.min(...fed.map((c) => c.born));
    return { mapping: firstFed + 1.8, feeding: d.growAt + 3, finale: d.duration + 0.4, grown: d.duration + 2.5 };
  });
}

const only = process.env.ONTAIX_SCENE?.split(',');

for (const scene of scenes) {
  if (only && !only.some((o) => scene.name.includes(o))) continue;
  for (const vp of scene.viewports) {
    const phone = vp === PHONE;
    const name = phone ? `phone-${scene.name}` : scene.name;
    test(`${name} · ${vp.width}x${vp.height}`, async ({ browser }) => {
      test.setTimeout(180_000);
      const ctx = await browser.newContext(phone ? { viewport: vp, isMobile: true, hasTouch: true, deviceScaleFactor: 1 } : { viewport: vp });
      const page = await ctx.newPage();
      try {
        await openStudio(page);
        const plan = await startDemo(page, phone);
        await advance(page, Math.round(scene.at(plan) * 1000));
        await expectScene(page, name, vp, phone ? { animations: 'disabled', caret: 'hide' } : {});
      } finally {
        await ctx.close();
      }
    });
  }
}
