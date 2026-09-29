/**
 * The three ways content enters the model: text typed in the teach bar, a speech transcript from
 * the teach bar microphone, and a document uploaded to the API. Each sentence goes through
 * `POST /teach/parse` and the drafts it returns are proposed; nothing is written without approval.
 * Captions and pacing follow reference/ontaix-studio-reference.html lines 864-903 (`teach`,
 * `importDocument`) on its import path, where no sentence is intercepted.
 */
import { api } from '../api/client';
import { ApiError, type ImportRef, type InputOrigin, type ProposalDraft, type TeachRequest, type TeachResult } from '../api/types';
import { drawBirth } from '../canvas/division';
import { random } from '../runtime/rng';
import { store } from '../store/store';

/** Pause between two imported sentences, as in the reference. */
const IMPORT_PACE_MS = 450;
/** The longest `Retry-After` a refused batch is retried after; a longer wait is shown as refused. */
const BATCH_RETRY_MAX_S = 60;

/** The teach bar session: a new one when the Studio loads and whenever the taught company changes. */
let session: { companyId: string; id: string } | null = null;

/** The session id for sentences taught to `companyId`, so the API can resolve back-references. */
export function teachSessionId(companyId: string): string {
  if (!session || session.companyId !== companyId) session = { companyId, id: uuid4() };
  return session.id;
}

/** A random version 4 uuid from the platform's crypto source; never the seeded canvas stream. */
function uuid4(): string {
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

/** Waits, or returns at once while animations are skipped. */
const wait = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, store.s.SKIP ? 0 : ms));

/**
 * Draws the random numbers a draft's birth consumes, in the reference order, and puts the link
 * bend on the draft for the server to store. Concept and spec drafts draw angle noise, node
 * seed and link seed; relation drafts draw the link seed only.
 */
export function withSeed<D extends ProposalDraft>(draft: D): D {
  if (draft.type === 'concept' || draft.type === 'spec') {
    const draws = drawBirth();
    store.rememberBirth(draft.companyId, draft.label, draws);
    return { ...draft, seed: draws.link };
  }
  if (draft.type === 'relation') return { ...draft, seed: random() };
  return draft;
}

/** Teaches the active company one typed or spoken sentence; an empty submission does nothing. */
export async function teach(text: string, origin: InputOrigin = 'text'): Promise<void> {
  text = text.trim();
  const co = store.s.activeCompany;
  if (!text || !co || !co.sid) return;
  await parseAndPropose({ companyId: co.sid, text, origin, sessionId: teachSessionId(co.sid) });
}

/** Teaches the active company one stored sentence of a document import. */
async function teachSentence(importRef: ImportRef): Promise<void> {
  const co = store.s.activeCompany;
  if (!co || !co.sid) return;
  await parseAndPropose({ companyId: co.sid, importRef, sessionId: teachSessionId(co.sid) });
}

async function parseAndPropose(request: TeachRequest): Promise<void> {
  let result: TeachResult;
  try {
    result = await api.teachParse(request);
  } catch (err) {
    store.refused(err);
    return;
  }
  // All drafts of one parse leave as one all-or-nothing batch.
  if (result.drafts.length) await submitBatch(result.drafts.map(withSeed));
  if (result.outcome === 'understood') {
    const n = result.statements?.length ?? result.drafts.length;
    store.caption(`Understood ${n === 1 ? 'one statement' : n + ' statements'}`, result.caption);
    return;
  }
  if (result.outcome === 'partly_understood') {
    store.caption('Partly understood', result.caption);
    return;
  }
  store.caption('Not understood', result.caption);
}

/** Submits one parse's drafts; a batch refused for the proposal budget is retried whole once
 * after its `Retry-After` when that is short, never split. */
async function submitBatch(drafts: ProposalDraft[]): Promise<void> {
  try {
    await api.createProposalBatch(drafts);
  } catch (err) {
    const wait = err instanceof ApiError && err.status === 429 ? err.retryAfter : null;
    if (wait === null || wait > BATCH_RETRY_MAX_S) {
      store.refused(err);
      return;
    }
    await new Promise((r) => setTimeout(r, wait * 1000));
    await api.createProposalBatch(drafts).catch((e) => store.refused(e));
  }
}

/** Uploads a document to the API, which extracts and stores its sentences; each is then taught like a spoken one. */
export async function importDocument(file: File | null | undefined): Promise<void> {
  if (!file || store.ui.importing) return;
  store.ui.importing = true;
  store.bump();
  try {
    const imported = await api.importSentences(file);
    const sents = imported.sentences;
    const before = store.ui.proposals.length;
    store.caption(
      'Importing ' + imported.fileName,
      `${sents.length} sentences found. Each one is read the way a spoken sentence is; what the model understands becomes a proposal.`,
    );
    for (let i = 0; i < sents.length; i++) {
      await teachSentence({ importId: imported.importId, sentenceIndex: i });
      await wait(IMPORT_PACE_MS);
    }
    await store.refreshProposals();
    const added = store.ui.proposals.length - before;
    store.caption(
      'Import finished',
      `${imported.fileName}: ${sents.length} sentences read, ${added} proposal${added === 1 ? '' : 's'} waiting for approval on the right.`,
    );
  } catch (err) {
    const reason = err instanceof ApiError ? err.problem.detail || err.problem.title : (err as Error).message;
    store.caption('Import failed', `${file.name} could not be read (${reason}). Text, Markdown, CSV, Word and PDF are supported.`);
  } finally {
    store.ui.importing = false;
    store.bump();
  }
}
