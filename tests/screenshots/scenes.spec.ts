/**
 * Screenshot regression: the reference file and the Studio, same seed, same clock, same
 * viewport, compared pixel for pixel at 0.1 percent tolerance.
 *
 * Scenes of this increment: empty canvas (the home company before it knows itself), first
 * company seeded (scene 1 played and approved), pending proposals visible (scene 1 played, not
 * approved), legend hidden. Each runs in dark and light at 1440x900 and 1920x1080.
 */
import { test, expect, type Page } from '../../apps/studio/test-support/playwright';
import {
  advance,
  compare,
  drawDivergence,
  fontsReady,
  openReference,
  openStudio,
  report,
  switchToLight,
  TOLERANCE,
  VIEWPORTS,
  type Theme,
} from './harness';

interface SceneScript {
  name: string;
  /** Drives one page from load to the frame under test. Both pages get the same script. */
  play: (page: Page) => Promise<void>;
}

/** Settles the page: fonts, then enough frames for the caption typer and the toggles to land. */
async function settle(page: Page, ms: number) {
  await fontsReady(page);
  await advance(page, ms);
}

const scenes: SceneScript[] = [
  {
    name: 'empty-canvas',
    play: async (page) => {
      await settle(page, 5000);
    },
  },
  {
    name: 'first-company-seeded',
    play: async (page) => {
      await settle(page, 500);
      await page.click('#skip');
      await page.keyboard.press('Space');
      await advance(page, 1500);
      await page.click('#approveAll');
      await advance(page, 4000);
    },
  },
  {
    name: 'pending-proposals',
    play: async (page) => {
      await settle(page, 500);
      await page.click('#skip');
      await page.keyboard.press('Space');
      await advance(page, 5000);
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

const themes: Theme[] = ['dark', 'light'];

for (const vp of VIEWPORTS) {
  for (const scene of scenes) {
    for (const theme of themes) {
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
          await scene.play(ref);
          await scene.play(studio);
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
