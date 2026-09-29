/**
 * Screenshot regression: the reference file and the Studio, same seed, same clock, same
 * viewport, compared pixel for pixel at 0.1 percent tolerance.
 *
 * The reference still contains its scripted story; the harness hides the story-only elements in
 * both pages and never plays a scene. Both pages are driven through the paths the product keeps:
 * sentences through teach (the reference's import path), documents through the file input,
 * companies through the add-company dialog, relations through the relationship box, decisions
 * through Approve all.
 *
 * Scenes: empty canvas (the home company's root only), a first model taught through text and
 * approved, pending proposals, a company added with its starter vocabulary pending, legend
 * hidden, each in dark and light at 1440x900 and 1920x1080; the full fixture model (text,
 * document import, a second company, equivalences, everything approved) in dark and light at
 * 1440x900.
 */
import { test, expect, type Page } from '../../apps/studio/test-support/playwright';
import {
  addCompanyWithStarter,
  advance,
  approveAll,
  beforeScreenshot,
  both,
  compare,
  drawDivergence,
  fontsReady,
  importText,
  openReference,
  openStudio,
  relate,
  report,
  switchToLight,
  teachFirstModel,
  TOLERANCE,
  VIEWPORTS,
  type Pair,
  type Theme,
  type Viewport,
} from './harness';

interface SceneScript {
  name: string;
  /** Drives both pages from load to the frame under test through the same user actions. */
  play: (pair: Pair) => Promise<void>;
  /** Viewports the scene runs at; every contract viewport when left out. */
  viewports?: Viewport[];
}

const HOME = 'Northwind Industries';
const AURORA = 'Aurora Valves';
const AURORA_SUB = 'industrial valves · 2 plants · 640 people';

/** A small document taught after the first model: each sentence names a concept already there. */
const DOCUMENT = 'Every sales order is billed by invoices. A customer holds contracts. Short line.';

/** Settles the page: fonts, then enough frames for the caption typer and the toggles to land. */
async function settle(page: Page, ms: number) {
  await fontsReady(page);
  await advance(page, ms);
}

const scenes: SceneScript[] = [
  {
    name: 'empty-canvas',
    play: (pair) => both(pair, (page) => settle(page, 5000)),
  },
  {
    name: 'first-model-approved',
    play: (pair) =>
      both(pair, async (page) => {
        await teachFirstModel(page);
        await advance(page, 1100);
        await approveAll(page);
        await advance(page, 4000);
      }),
  },
  {
    name: 'pending-proposals',
    play: (pair) =>
      both(pair, async (page) => {
        await teachFirstModel(page);
        await advance(page, 5000);
      }),
  },
  {
    name: 'company-added',
    play: (pair) =>
      both(pair, async (page) => {
        await settle(page, 500);
        await page.click('#skip');
        await addCompanyWithStarter(page, AURORA, AURORA_SUB);
        await advance(page, 5000);
      }),
  },
  {
    name: 'full-fixture-model',
    viewports: [VIEWPORTS[0]],
    play: async (pair) => {
      await both(pair, async (page) => {
        await teachFirstModel(page);
        await importText(page, 'northwind-sales.txt', DOCUMENT);
        await advance(page, 1000);
        await approveAll(page);
        await advance(page, 2000);
        await addCompanyWithStarter(page, AURORA, AURORA_SUB);
        await advance(page, 1500);
        await approveAll(page);
        await advance(page, 3000);
      });
      for (const [a, b] of [
        ['Client', 'Customer'],
        ['Client order', 'Sales order'],
        ['Article', 'Product'],
      ]) {
        await relate(pair, [a, AURORA], [b, HOME], 'equivalent to');
        await both(pair, (page) => advance(page, 400));
      }
      await both(pair, async (page) => {
        await approveAll(page);
        await advance(page, 6000);
      });
    },
  },
  {
    name: 'legend-hidden',
    play: (pair) =>
      both(pair, async (page) => {
        await settle(page, 500);
        await page.keyboard.press('l');
        await advance(page, 4500);
      }),
  },
];

const themes: Theme[] = ['dark', 'light'];
/** Optional filters for a partial run: scene name fragments (comma-separated), one viewport, one theme. */
const only = process.env.ONTAIX_SCENE?.split(',');
const onlyViewport = process.env.ONTAIX_VIEWPORT;
const onlyTheme = process.env.ONTAIX_THEME;

for (const vp of VIEWPORTS) {
  if (onlyViewport && onlyViewport !== `${vp.width}x${vp.height}`) continue;
  for (const scene of scenes) {
    if (scene.viewports && !scene.viewports.includes(vp)) continue;
    if (only && !only.some((o) => scene.name.includes(o))) continue;
    for (const theme of themes) {
      if (onlyTheme && onlyTheme !== theme) continue;
      test(`${scene.name} · ${theme} · ${vp.width}x${vp.height}`, async ({ browser }, info) => {
        const refCtx = await browser.newContext({ viewport: vp });
        const studioCtx = await browser.newContext({ viewport: vp });
        const ref = await refCtx.newPage();
        const studio = await studioCtx.newPage();
        try {
          await openReference(ref);
          await openStudio(studio);
          if (theme === 'light') {
            await switchToLight(ref);
            await switchToLight(studio);
          }
          await scene.play({ ref, studio });
          await beforeScreenshot(ref, studio);
          const [a, b] = await Promise.all([ref.screenshot({ type: 'png' }), studio.screenshot({ type: 'png' })]);
          const c = compare(scene.name, theme, vp, a, b);
          report(info, scene.name, theme, vp, c);
          const draws = await drawDivergence(ref, studio);
          info.annotations.push({ type: 'draws', description: draws });
          expect(
            c.diffRatio,
            `${scene.name} ${theme} ${vp.width}x${vp.height} differs by ${(c.diffRatio * 100).toFixed(4)} %; ${draws}`,
          ).toBeLessThanOrEqual(TOLERANCE);
        } finally {
          await refCtx.close();
          await studioCtx.close();
        }
      });
    }
  }
}
