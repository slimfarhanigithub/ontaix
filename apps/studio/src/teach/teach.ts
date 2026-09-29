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
import { bySid } from '../canvas/state';
import type { Node } from '../canvas/types';
import { random } from '../runtime/rng';
import { store } from '../store/store';
import { readWholeDocument } from './wholeDocument';

/** Pause between two imported sentences, as in the reference. */
const IMPORT_PACE_MS = 450;
/** Pause after the whole-document failure caption, before sentence by sentence begins. */
const FALLBACK_PAUSE_MS = 1500;
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

/** The refusals of a batch that name a fact the model already holds. */
const DUPLICATE_CODES = new Set(['duplicate_label', 'duplicate_relation']);

/** Submits one parse's drafts; a batch refused for the proposal budget is retried whole once
 * after its `Retry-After` when that is short, never split. A batch refused because a draft
 * restates a fact already in the model is sent once more without the drafts the canvas shows
 * as already there, so the new facts of the parse are still proposed; a toast names what was
 * left out. */
async function submitBatch(drafts: ProposalDraft[]): Promise<void> {
  try {
    await api.createProposalBatch(drafts);
  } catch (err) {
    if (err instanceof ApiError && err.status === 409 && DUPLICATE_CODES.has(err.problem.code)) {
      const plan = withoutKnown(drafts);
      if (!plan.fresh.length || !plan.known.length) {
        store.refused(err);
        return;
      }
      try {
        await api.createProposalBatch(plan.fresh);
      } catch (e) {
        store.refused(e);
        return;
      }
      store.toast2('Already there', leftOutText(plan));
      return;
    }
    const wait = err instanceof ApiError && err.status === 429 ? err.retryAfter : null;
    if (wait === null || wait > BATCH_RETRY_MAX_S) {
      store.refused(err);
      return;
    }
    await new Promise((r) => setTimeout(r, wait * 1000));
    await api.createProposalBatch(drafts).catch((e) => store.refused(e));
  }
}

/** A refused batch split for its one resubmission. */
export interface DuplicatePlan {
  /** The drafts sent again, children re-pointed to the existing concept where it stands under the same parent. */
  fresh: ProposalDraft[];
  /** Names of the drafts left out because the model already holds them. */
  known: string[];
  /** Labels of the drafts left out because they named a left-out concept that stands under another parent. */
  orphaned: string[];
}

/** Relation actions compared as the API compares them: NFKC, whitespace collapsed, trimmed, lower case. */
const normaliseAction = (action: string): string => action.normalize('NFKC').replace(/\s+/g, ' ').trim().toLowerCase();

/** A concept of the company carrying the label, ignoring case; cells being deleted do not count, as in the API. */
function liveConcept(companyId: string, label: string): Node | null {
  const company = store.companyBySid(companyId);
  if (!company) return null;
  const wanted = label.toLowerCase();
  return (
    store.s.nodes.find((n) => n.company === company && n.kind !== 'source' && !n.dying && n.label.toLowerCase() === wanted) ||
    null
  );
}

/** True when the canvas already holds what the draft proposes: a live concept of that label in its
 * company, or a live relation with the same ends and action. */
export function alreadyInModel(draft: ProposalDraft): boolean {
  const s = store.s;
  if (draft.type === 'concept' || draft.type === 'spec') return !!liveConcept(draft.companyId, draft.label);
  if (draft.type === 'relation') {
    const a = bySid(s, draft.aId),
      b = bySid(s, draft.bId);
    if (!a || !b || a.dying || b.dying) return false;
    const action = normaliseAction(draft.action);
    return s.links.some((l) => !l.dying && l.a === a && l.b === b && normaliseAction(l.label) === action);
  }
  return false;
}

/**
 * Leaves out the drafts the canvas already holds. A later draft that names a left-out concept by
 * label is re-pointed to the existing concept when that concept stands under the same parent the
 * draft taught; otherwise it is left out too, and so are the drafts that name it in turn.
 */
export function withoutKnown(drafts: ProposalDraft[]): DuplicatePlan {
  const plan: DuplicatePlan = { fresh: [], known: [], orphaned: [] };
  // Label (lower case) of a left-out concept draft: the existing node it maps to, or null when its children are left out.
  const replaced = new Map<string, Node | null>();
  const key = (label: string | undefined): string | undefined => label?.toLowerCase();
  for (const d of drafts) {
    const via = d.type === 'concept' || d.type === 'spec' ? key(d.parentLabel) : undefined;
    const ends = d.type === 'relation' ? [key(d.aLabel), key(d.bLabel)] : [];
    if ((via && replaced.get(via) === null) || ends.some((e) => e && replaced.get(e) === null)) {
      plan.orphaned.push(draftName(d));
      if (d.type === 'concept' || d.type === 'spec') replaced.set(d.label.toLowerCase(), null);
      continue;
    }
    let draft = d;
    if ((draft.type === 'concept' || draft.type === 'spec') && via && replaced.get(via)?.sid) {
      const { parentLabel: _, ...rest } = draft;
      draft = { ...rest, parentId: replaced.get(via)!.sid! } as ProposalDraft;
    }
    if (draft.type === 'relation') {
      const a = key(draft.aLabel),
        b = key(draft.bLabel);
      const { aLabel, bLabel, ...rest } = draft;
      const aNode = a ? replaced.get(a) : undefined,
        bNode = b ? replaced.get(b) : undefined;
      draft = {
        ...rest,
        ...(aNode?.sid ? { aId: aNode.sid } : aLabel !== undefined ? { aLabel } : {}),
        ...(bNode?.sid ? { bId: bNode.sid } : bLabel !== undefined ? { bLabel } : {}),
      } as ProposalDraft;
    }
    if (!alreadyInModel(draft)) {
      plan.fresh.push(draft);
      continue;
    }
    plan.known.push(draftName(draft));
    if (draft.type === 'concept' || draft.type === 'spec') {
      const existing = liveConcept(draft.companyId, draft.label);
      const taught = draft.parentLabel ? liveConcept(draft.companyId, draft.parentLabel) : bySid(store.s, draft.parentId);
      replaced.set(draft.label.toLowerCase(), existing && taught && existing.parent === taught ? existing : null);
    }
  }
  return plan;
}

/** A draft's name for the toast: a concept's label, or a relation's words. */
function draftName(d: ProposalDraft): string {
  if (d.type === 'concept' || d.type === 'spec') return d.label;
  if (d.type === 'relation') {
    const a = bySid(store.s, d.aId)?.label ?? d.aLabel ?? '',
      b = bySid(store.s, d.bId)?.label ?? d.bLabel ?? '';
    return `${a} ${normaliseAction(d.action)} ${b}`.trim();
  }
  return d.type;
}

/** The toast text naming what a resubmission left out. */
export function leftOutText(plan: DuplicatePlan): string {
  const known = `Left out, already in the model: ${plan.known.join(', ')}.`;
  return plan.orphaned.length
    ? `${known} Also left out, as the existing concept stands under another parent: ${plan.orphaned.join(', ')}.`
    : known;
}

/** How an imported document is read: sentence by sentence, as a whole by the model, or as an ontology. */
export type ImportMode = 'sentences' | 'document' | 'ontology';

/**
 * Uploads a document to the API, which extracts and stores its sentences. Sentence by sentence,
 * each is then taught like a spoken one; as a whole, the API maps the document into one tree of
 * proposals, and the sentences are taught one by one when that reading is not available.
 */
export async function importDocument(file: File | null | undefined, mode: ImportMode = 'sentences'): Promise<void> {
  if (!file || store.ui.importing) return;
  // TODO: route `ontology` to ontology import (POST /ontology-imports) once that path lands.
  if (mode === 'ontology') return;
  store.ui.importing = true;
  store.bump();
  try {
    const imported = await api.importSentences(file);
    const co = store.s.activeCompany;
    if (mode === 'document' && co?.sid) {
      if ((await readWholeDocument(imported, co.sid)) !== 'unavailable') return;
      // The failure caption stays readable before the sentence-by-sentence captions replace it.
      await wait(FALLBACK_PAUSE_MS);
    }
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
