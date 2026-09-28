/**
 * The Studio against the real API on the local stack: both seeded companies render with the
 * concept counts the API reports, a Builder teaches one concept, a Governor approves it, and
 * the cell turns green while its domain product's revision goes up.
 */
import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test, type Page } from '../../apps/studio/test-support/playwright';

const here = dirname(fileURLToPath(import.meta.url));
const OUTPUT_DIR = resolve(here, 'output');

const BUILDER = 'sam.okafor@northwind.com';
const GOVERNOR = 'hugo.brandt@northwind.com';
const GREEN = '#4fc98f';
/** Names an existing Northwind concept and nothing the next story scene listens for. */
const SENTENCE = 'Invoice has due date';
const TAUGHT = 'Due date';

interface ApiCompany {
  id: string;
  name: string;
  counts: { concepts: number };
}

/** Concept cells per company name, read from the store the test hooks expose. */
function conceptCounts(page: Page): Promise<Record<string, number>> {
  return page.evaluate(() => {
    const { store } = (window as unknown as { __ontaix: { store: { s: { nodes: { kind: string; company: { name: string } | null }[] } } } }).__ontaix;
    const counts: Record<string, number> = {};
    for (const n of store.s.nodes) {
      if (n.kind !== 'concept' || !n.company) continue;
      counts[n.company.name] = (counts[n.company.name] || 0) + 1;
    }
    return counts;
  });
}

async function openStudio(page: Page, user: string): Promise<void> {
  await page.goto(`/?seed=7&user=${encodeURIComponent(user)}`);
  await page.waitForFunction(() => document.documentElement.dataset.ontaixReady !== undefined);
  expect(await page.evaluate(() => document.documentElement.dataset.ontaixReady)).toBe('ready');
}

test('Studio shows Northwind and Aurora from the real API, and a taught concept is approved', async ({ browser, request }) => {
  const scene = await (await request.get('/api/v1/scene', { headers: { 'X-Ontaix-User': GOVERNOR } })).json();
  const companies = scene.companies as ApiCompany[];
  const expected = Object.fromEntries(companies.map((c) => [c.name, c.counts.concepts]));
  expect(Object.keys(expected)).toEqual(expect.arrayContaining(['Northwind Industries', expect.stringMatching(/^Aurora/)]));

  // Both companies render, with the API's concept counts.
  const governor = await browser.newPage();
  await openStudio(governor, GOVERNOR);
  await expect(governor.locator('#companySel option')).toHaveText(companies.map((c) => c.name));
  expect(await conceptCounts(governor)).toEqual(expected);
  await governor.waitForTimeout(4000);
  mkdirSync(OUTPUT_DIR, { recursive: true });
  await governor.screenshot({ path: resolve(OUTPUT_DIR, 'studio-both-companies.png') });

  // A Builder teaches one concept; it divides off Invoice as a pending cell.
  const builder = await browser.newPage();
  await openStudio(builder, BUILDER);
  await builder.locator('#say').fill(SENTENCE);
  await builder.locator('#teach').click();
  await expect(builder.locator('#propList .prop')).toHaveCount(1);
  await expect(builder.locator('#propList .prop .what')).toContainText(TAUGHT);
  await builder.close();

  // The Governor sees it after a reload and approves it. The fake clock runs until paused below.
  await governor.clock.install();
  await governor.reload();
  await governor.waitForFunction(() => document.documentElement.dataset.ontaixReady === 'ready');
  const before = await governor.evaluate((label) => {
    const { store } = (window as unknown as { __ontaix: { store: { s: { nodes: { label: string; pending: boolean; domain: { version: number } | null }[] } } } }).__ontaix;
    const n = store.s.nodes.find((x) => x.label === label);
    return n ? { pending: n.pending, version: n.domain?.version ?? null } : null;
  }, TAUGHT);
  expect(before).toEqual({ pending: true, version: expect.any(Number) });

  // Freeze frames so the 0.9 s green flash is still on the cell when it is read.
  await governor.clock.pauseAt(new Date(Date.now() + 1000));
  const row = governor.locator('#propList .prop', { hasText: TAUGHT });
  await row.locator('button.ok').click();
  await expect(governor.locator('#propList .prop')).toHaveCount(0);
  const after = await governor.evaluate((label) => {
    const { store } = (window as unknown as { __ontaix: { store: { s: { nodes: { label: string; pending: boolean; flash: { color: string } | null; domain: { version: number } | null }[] } } } }).__ontaix;
    const n = store.s.nodes.find((x) => x.label === label);
    return n ? { pending: n.pending, flash: n.flash?.color ?? null, version: n.domain?.version ?? null } : null;
  }, TAUGHT);
  expect(after?.pending).toBe(false);
  expect(after?.flash).toBe(GREEN);
  expect(after?.version).toBeGreaterThan(before!.version as number);
  await governor.close();
});
