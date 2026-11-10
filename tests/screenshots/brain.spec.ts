/**
 * Screenshot regression of the demo brain built on a first model, same seed and fake clock as the
 * canvas scenes, compared with its stored baseline at 0.1 percent tolerance.
 *
 * Scenes, each a moment of the demo's own plan: the new concepts mapped to the sources close up
 * (1.8 s after the first one buds); the brain growing, its cores plugged in (3 s into the growth);
 * the data run lighting the third lobe; the first agent's question, its route lit; its proposal
 * just approved; every agent at work (1 s after the demo has played). The growing brain and the
 * agents at work run at 1440x900 and on a phone (390x844, touch); the mapping too; the others at
 * 1440x900.
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
  plugged: number;
  run: number;
  question: number;
  approved: number;
  agents: number;
}

interface BrainScene {
  name: string;
  /** Seconds after the demo starts at which the frame is taken. */
  at: (p: Plan) => number;
  viewports: Viewport[];
}

const scenes: BrainScene[] = [
  { name: 'brain-mapping', at: (p) => p.mapping, viewports: [DESKTOP, PHONE] },
  { name: 'brain-plugged', at: (p) => p.plugged, viewports: [DESKTOP, PHONE] },
  { name: 'brain-run', at: (p) => p.run, viewports: [DESKTOP] },
  { name: 'brain-question', at: (p) => p.question, viewports: [DESKTOP] },
  { name: 'brain-approved', at: (p) => p.approved, viewports: [DESKTOP] },
  { name: 'brain-agents', at: (p) => p.agents, viewports: [DESKTOP, PHONE] },
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
    type Demo = {
      stories: number;
      growAt: number;
      duration: number;
      cells: { born: number; story: { source: boolean } | null }[];
      rig: { runs: { at: number }[]; question: { answerAt: number }; proposal: { approveAt: number } };
    };
    const d = (window as unknown as { __ontaix: { store: { s: { brain: Demo } } } }).__ontaix.store.s.brain;
    const mapped = d.cells.slice(0, d.stories).filter((c) => !c.story?.source);
    const firstMapped = Math.min(...mapped.map((c) => c.born));
    return {
      mapping: firstMapped + 1.8,
      plugged: d.growAt + 3,
      run: d.rig.runs[2].at + 0.9,
      question: d.rig.question.answerAt - 0.7,
      approved: d.rig.proposal.approveAt + 0.3,
      agents: d.duration + 1,
    };
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
