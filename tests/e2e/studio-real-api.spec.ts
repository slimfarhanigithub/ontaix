/**
 * The Studio against the real API on the local stack: both seeded companies render with the
 * concept counts the API reports, a Builder teaches one concept, a Governor approves it, and
 * the cell turns green while its domain product's revision goes up. A Builder then draws one
 * relation between two approved cells through the link dialog and a Governor approves it.
 */
import { mkdirSync } from 'node:fs';
import { GREEN } from '../../apps/studio/src/canvas/constants';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test, type Page } from '../../apps/studio/test-support/playwright';

const here = dirname(fileURLToPath(import.meta.url));
const OUTPUT_DIR = resolve(here, 'output');

const BUILDER = 'sam.okafor@northwind.com';
const GOVERNOR = 'hugo.brandt@northwind.com';
/** Names an existing Northwind concept and one new one. */
const SENTENCE = 'Invoice has due date';
const TAUGHT = 'Due date';
/** The taught cell and the cell it divided off, joined by an action they do not hold yet. */
const RELATION = { a: TAUGHT, b: 'Invoice', action: 'is printed on' };

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

test('Studio shows Northwind and Aurora from the real API, a taught concept and a drawn relation are approved', async ({ browser, request }) => {
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
  await expect(builder.locator('#propList .prop', { hasText: TAUGHT })).toHaveCount(1);
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
  await expect(row).toHaveCount(0);
  const after = await governor.evaluate((label) => {
    const { store } = (window as unknown as { __ontaix: { store: { s: { nodes: { label: string; pending: boolean; flash: { color: string } | null; domain: { version: number } | null }[] } } } }).__ontaix;
    const n = store.s.nodes.find((x) => x.label === label);
    return n ? { pending: n.pending, flash: n.flash?.color ?? null, version: n.domain?.version ?? null } : null;
  }, TAUGHT);
  expect(after?.pending).toBe(false);
  expect(after?.flash).toBe(GREEN);
  expect(after?.version).toBeGreaterThan(before!.version as number);
  await governor.close();

  // A Builder draws a relation through the link dialog; the draft reaches the API by ids.
  const drawer = await browser.newPage();
  await openStudio(drawer, BUILDER);
  await drawer.evaluate(({ a, b }) => {
    type N = { label: string; kind: string; company: { name: string } | null };
    const { store } = (window as unknown as { __ontaix: { store: { s: { nodes: N[] }; openLinkBox(a: N, b: N, x: number, y: number): void } } }).__ontaix;
    const find = (label: string) => store.s.nodes.find((n) => n.label === label && n.company?.name === 'Northwind Industries')!;
    store.openLinkBox(find(a), find(b), 400, 300);
  }, RELATION);
  await drawer.locator('#lbAction').fill(RELATION.action);
  await drawer.locator('#lbAction').press('Enter');
  const drawn = drawer.locator('#propList .prop', { hasText: RELATION.action });
  await expect(drawn).toHaveCount(1);
  await drawer.close();

  // The Governor approves it and the relation is no longer pending.
  const approver = await browser.newPage();
  await openStudio(approver, GOVERNOR);
  const relationRow = approver.locator('#propList .prop', { hasText: RELATION.action });
  await expect(relationRow).toHaveCount(1);
  await relationRow.locator('button.ok').click();
  await expect(relationRow).toHaveCount(0);
  await expect
    .poll(() =>
      approver.evaluate(({ a, b, action }) => {
        type L = { label: string; pending: boolean; a: { label: string }; b: { label: string } };
        const { store } = (window as unknown as { __ontaix: { store: { s: { links: L[] } } } }).__ontaix;
        const l = store.s.links.find((x) => x.label === action && x.a.label === a && x.b.label === b);
        return l ? l.pending : null;
      }, RELATION),
    )
    .toBe(false);
  await approver.close();
});
