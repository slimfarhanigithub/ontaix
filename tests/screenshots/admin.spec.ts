/**
 * Screenshot regression of the admin portal: every page, the data-source wizard steps 1 to 3,
 * the relationship dialog opened from the Relationships page and the typed-"disable"
 * confirmation. The reference file and the Studio run the same script under the same seed and
 * clock and are compared pixel for pixel at 0.1 percent tolerance.
 *
 * Every scene starts from a first model taught through text and approved. CSS animations
 * (window and dialog entrances, spinners) do not follow the fake clock, so screenshots are taken
 * with animations finished on both pages.
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
} from './harness';

interface SceneScript {
  name: string;
  /** Drives both pages through the same user actions. */
  play: (pair: Pair) => Promise<void>;
}

/** A first model taught through text and approved: one company with its first concepts. */
async function seeded(page: Page) {
  await teachFirstModel(page);
  await advance(page, 1100);
  await approveAll(page);
  await advance(page, 4000);
}

/** Opens the portal on a page and lets the page settle. */
async function adminPage(page: Page, id: string) {
  await page.keyboard.press('g');
  await advance(page, 100);
  await page.click(`#adminNav button[data-page="${id}"]`);
  await advance(page, 600);
}

const PAGES: [string, string][] = [
  ['overview', 'overview'],
  ['settings', 'tenant-settings'],
  ['appearance', 'appearance'],
  ['sources', 'data-sources'],
  ['connectors', 'connectors'],
  ['entities', 'entities'],
  ['relations', 'relationships'],
  ['bindings', 'bindings'],
  ['companies', 'companies'],
  ['domains', 'domain-products'],
  ['groups', 'groups'],
  ['users', 'users'],
  ['roles', 'roles'],
  ['audit', 'audit-log'],
  ['agents', 'cost-management'],
];

const scenes: SceneScript[] = [
  ...PAGES.map(
    ([id, name]): SceneScript => ({
      name: `admin-${name}`,
      play: (pair) =>
        both(pair, async (page) => {
          await seeded(page);
          await adminPage(page, id);
        }),
    }),
  ),
  {
    name: 'wizard-step-1',
    play: (pair) =>
      both(pair, async (page) => {
        await seeded(page);
        await adminPage(page, 'sources');
        await page.click('#adminMain [data-act="add"]');
        await advance(page, 600);
      }),
  },
  {
    name: 'wizard-step-2',
    play: (pair) =>
      both(pair, async (page) => {
        await seeded(page);
        await adminPage(page, 'sources');
        await page.click('#adminMain [data-act="add"]');
        await advance(page, 300);
        await page.click('#wzCat .c[data-k="SAP"]');
        await advance(page, 100);
        await page.click('.dlg .df .btn.primary');
        await advance(page, 600);
      }),
  },
  {
    name: 'wizard-step-3',
    play: (pair) =>
      both(pair, async (page) => {
        await seeded(page);
        await adminPage(page, 'sources');
        await page.click('#adminMain [data-act="add"]');
        await advance(page, 300);
        await page.click('#wzCat .c[data-k="SAP"]');
        await advance(page, 100);
        await page.click('.dlg .df .btn.primary');
        await advance(page, 300);
        await page.click('.dlg .df .btn.primary');
        await advance(page, 1600);
      }),
  },
  {
    name: 'relationship-dialog',
    play: (pair) =>
      both(pair, async (page) => {
        await seeded(page);
        await adminPage(page, 'relations');
        await page.click('#lstRelations tbody tr:first-child button[data-fn="edit"]');
        await advance(page, 1500);
      }),
  },
  {
    name: 'disable-confirmation',
    play: async (pair) => {
      await both(pair, async (page) => {
        await seeded(page);
        await addCompanyWithStarter(page, 'Aurora Valves', 'industrial valves · 2 plants · 640 people');
        await advance(page, 1500);
        await approveAll(page);
        await advance(page, 3000);
      });
      await relate(pair, ['Client', 'Aurora Valves'], ['Customer', 'Northwind Industries'], 'equivalent to');
      await both(pair, async (page) => {
        await advance(page, 1000);
        await adminPage(page, 'settings');
        await page.click('#adminMain .tg[data-set="crossCompany"]');
        await advance(page, 300);
        await page.keyboard.type('disable');
        await advance(page, 300);
      });
    },
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
          const shot = { type: 'png' as const, animations: 'disabled' as const, caret: 'hide' as const };
          const [a, b] = await Promise.all([ref.screenshot(shot), studio.screenshot(shot)]);
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
