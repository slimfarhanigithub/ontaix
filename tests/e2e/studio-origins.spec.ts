/**
 * Content enters the Studio three ways against the real API: a Builder types a sentence
 * (origin `text`), speaks one (the microphone's final transcript, origin `speech`), and imports a
 * text file and a Word document (origin `document`, with the file name, media type, sentence
 * index and position the server copied from its stored import). A Governor approves one proposal
 * of each origin in the Studio, and the audit log records the origin of each decision.
 */
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test, type APIRequestContext, type Page } from '../../apps/studio/test-support/playwright';

const here = dirname(fileURLToPath(import.meta.url));
const FIXTURES = resolve(here, 'fixtures');

const BUILDER = 'sam.okafor@northwind.com';
const GOVERNOR = 'hugo.brandt@northwind.com';
const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

/** Each sentence names an existing Northwind concept and one new one. */
const TYPED = { sentence: 'A shipment has pallets.', taught: 'Pallet' };
const SPOKEN = { transcript: 'A warehouse has loading docks', taught: 'Loading dock' };
const TEXT_FILE = { file: 'northwind-logistics.txt', taught: 'Tracking number' };
const WORD_FILE = { file: 'northwind-purchasing.docx', taught: 'Payment term' };

interface ApiProposal {
  id: string;
  title: string;
  state: string;
  origin: 'text' | 'speech' | 'document';
  originDetail: { fileName: string; mediaType: string; sentenceIndex: number; position?: { unit: string; index: number } } | null;
}

/**
 * A stand-in for the browser's speech recognition: `start` reports the transcript the test set
 * on `window.__transcript` as one final result, the way the recogniser ends an utterance.
 */
const FAKE_SPEECH = `(() => {
  class FakeRecognition {
    constructor() { this.onstart = null; this.onresult = null; this.onerror = null; this.onend = null; }
    start() {
      setTimeout(() => {
        this.onstart && this.onstart();
        const result = [{ transcript: window.__transcript || '' }];
        result.isFinal = true;
        this.onresult && this.onresult({ results: [result] });
        this.onend && this.onend();
      }, 0);
    }
    stop() { this.onend && this.onend(); }
  }
  window.SpeechRecognition = FakeRecognition;
  window.webkitSpeechRecognition = FakeRecognition;
})();`;

async function openStudio(page: Page, user: string): Promise<void> {
  await page.goto(`/?seed=7&user=${encodeURIComponent(user)}`);
  await page.waitForFunction(() => document.documentElement.dataset.ontaixReady !== undefined);
  expect(await page.evaluate(() => document.documentElement.dataset.ontaixReady)).toBe('ready');
}

async function openProposals(request: APIRequestContext): Promise<ApiProposal[]> {
  const res = await request.get('/api/v1/proposals?pageSize=200', { headers: { 'X-Ontaix-User': GOVERNOR } });
  expect(res.ok()).toBe(true);
  return ((await res.json()) as { items: ApiProposal[] }).items;
}

/**
 * Imports a document read sentence by sentence. A detected document is read whole first; the
 * test answers the whole-document job with `503`, so the Studio falls back to sentence by
 * sentence whether or not the stack has a model configured.
 */
async function importFile(page: Page, file: string): Promise<void> {
  await page.route('**/api/v1/import/*/extraction', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/problem+json',
      body: JSON.stringify({ title: 'Unavailable', status: 503, code: 'unavailable', detail: 'not in this test' }),
    }),
  );
  await page.setInputFiles('#importFile', resolve(FIXTURES, file));
  await expect(page.locator('#captionKicker')).toHaveText('Import finished', { timeout: 30_000 });
}

test('text, speech and document imports become proposals with their origin, and one of each is approved', async ({ browser, request }) => {
  const builderContext = await browser.newContext();
  await builderContext.addInitScript(FAKE_SPEECH);
  const builder = await builderContext.newPage();
  await openStudio(builder, BUILDER);
  const row = (label: string) => builder.locator('#propList .prop', { hasText: label });

  // Typed text.
  await builder.locator('#say').fill(TYPED.sentence);
  await builder.locator('#teach').click();
  await expect(row(TYPED.taught)).toHaveCount(1);

  // Speech: the microphone's final transcript is taught as it is heard.
  await builder.evaluate((t) => ((window as unknown as { __transcript: string }).__transcript = t), SPOKEN.transcript);
  await builder.locator('#mic').click();
  await expect(row(SPOKEN.taught)).toHaveCount(1);

  // Documents: the API extracts and stores the sentences, the Studio teaches each by reference.
  await importFile(builder, TEXT_FILE.file);
  await expect(row(TEXT_FILE.taught)).toHaveCount(1);
  await importFile(builder, WORD_FILE.file);
  await expect(row(WORD_FILE.taught)).toHaveCount(1);
  await builderContext.close();

  const open = await openProposals(request);
  const byTitle = (title: string) => {
    const found = open.filter((p) => p.title === title);
    expect(found, `one open proposal titled ${title} among ${open.map((p) => p.title).join(', ')}`).toHaveLength(1);
    return found[0];
  };
  const typed = byTitle(TYPED.taught);
  const spoken = byTitle(SPOKEN.taught);
  const fromText = byTitle(TEXT_FILE.taught);
  const fromWord = byTitle(WORD_FILE.taught);
  expect([typed.origin, typed.originDetail]).toEqual(['text', null]);
  expect([spoken.origin, spoken.originDetail]).toEqual(['speech', null]);
  expect(fromText.origin).toBe('document');
  expect(fromText.originDetail).toMatchObject({ fileName: TEXT_FILE.file, mediaType: 'text/plain', sentenceIndex: 0 });
  expect(fromWord.origin).toBe('document');
  expect(fromWord.originDetail).toMatchObject({
    fileName: WORD_FILE.file,
    mediaType: DOCX,
    sentenceIndex: 0,
    position: { unit: 'paragraph', index: 2 },
  });

  // A Governor approves one proposal of each origin from the changes panel.
  const governor = await browser.newPage();
  await openStudio(governor, GOVERNOR);
  for (const p of [typed, spoken, fromText, fromWord]) {
    const pending = governor.locator('#propList .prop', { hasText: p.title });
    await expect(pending).toHaveCount(1);
    await pending.locator('button.ok').click();
    await expect(pending).toHaveCount(0);
  }
  await governor.close();

  for (const p of [typed, spoken, fromText, fromWord]) {
    const res = await request.get(`/api/v1/proposals/${p.id}`, { headers: { 'X-Ontaix-User': GOVERNOR } });
    const decided = (await res.json()) as ApiProposal;
    expect([decided.title, decided.state, decided.origin]).toEqual([p.title, 'approved', p.origin]);
  }
  const audit = await request.get('/api/v1/audit?pageSize=200', { headers: { 'X-Ontaix-User': GOVERNOR } });
  expect(audit.ok()).toBe(true);
  const entries = ((await audit.json()) as { items: { proposalId: string | null; origin: string | null; ok: boolean }[] }).items;
  for (const p of [typed, spoken, fromText, fromWord])
    expect(entries.find((e) => e.proposalId === p.id && e.ok)?.origin, `audit origin of ${p.title}`).toBe(p.origin);
});
