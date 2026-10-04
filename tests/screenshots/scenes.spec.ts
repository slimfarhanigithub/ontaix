/**
 * Screenshot regression of the canvas scenes: the Studio, same seed, same clock, same viewport,
 * compared with its stored baseline at 0.1 percent tolerance.
 *
 * The Studio is driven through the paths the product keeps: sentences through teach, documents
 * through the file input, companies through the add-company dialog, relations through the
 * relationship box, decisions through Approve all.
 *
 * Scenes: empty canvas (the home company's root only), a first model taught through text and
 * approved, pending proposals, a company added with its starter vocabulary pending, legend
 * hidden, each in light and dark at 1440x900 and 1920x1080; the full fixture model (text,
 * document import, a second company, equivalences, everything approved) in light and dark at
 * 1440x900.
 *
 * `--update-snapshots` writes the baselines of the running platform.
 */
import { test, type Page } from '../../apps/studio/test-support/playwright';
import {
  addCompanyWithStarter,
  advance,
  approveAll,
  expectScene,
  fontsReady,
  importText,
  openStudio,
  relate,
  teachFirstModel,
  useTheme,
  VIEWPORTS,
  type Theme,
  type Viewport,
} from './harness';

interface SceneScript {
  name: string;
  /** Drives the page from load to the frame under test. */
  play: (page: Page) => Promise<void>;
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
    play: (page) => settle(page, 5000),
  },
  {
    name: 'first-model-approved',
    play: async (page) => {
      await teachFirstModel(page);
      await advance(page, 1100);
      await approveAll(page);
      await advance(page, 4000);
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
    name: 'company-added',
    play: async (page) => {
      await settle(page, 500);
      await page.keyboard.press('s');
      await addCompanyWithStarter(page, AURORA, AURORA_SUB);
      await advance(page, 5000);
    },
  },
  {
    name: 'full-fixture-model',
    viewports: [VIEWPORTS[0]],
    play: async (page) => {
      await teachFirstModel(page);
      await importText(page, 'northwind-sales.txt', DOCUMENT);
      await advance(page, 1000);
      await approveAll(page);
      await advance(page, 2000);
      await addCompanyWithStarter(page, AURORA, AURORA_SUB);
      await advance(page, 1500);
      await approveAll(page);
      await advance(page, 3000);
      for (const [a, b] of [
        ['Client', 'Customer'],
        ['Client order', 'Sales order'],
        ['Article', 'Product'],
      ]) {
        await relate(page, [a, AURORA], [b, HOME], 'equivalent to');
        await advance(page, 400);
      }
      await approveAll(page);
      await advance(page, 6000);
    },
  },
  {
    name: 'legend-hidden',
    play: async (page) => {
      await settle(page, 500);
      await page.keyboard.press('l');
      await advance(page, 4500);
    },
  },
];

const themes: Theme[] = ['light', 'dark'];
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
      test(`${scene.name} · ${theme} · ${vp.width}x${vp.height}`, async ({ browser }) => {
        const ctx = await browser.newContext({ viewport: vp });
        const page = await ctx.newPage();
        try {
          await openStudio(page);
          await useTheme(page, theme);
          await scene.play(page);
          await expectScene(page, scene.name, theme, vp);
        } finally {
          await ctx.close();
        }
      });
    }
  }
}
