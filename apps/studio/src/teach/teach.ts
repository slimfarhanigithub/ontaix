/**
 * The three ways content enters the model: text typed in the teach bar, sentences spoken into the
 * teach bar microphone, and a document uploaded to the API. Each sentence goes through
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
import { importOntology } from './ontology';
import { beginProcessing } from './processing';
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

/**
 * Teaches the active company one typed or spoken sentence. Resolves true once the sentence is
 * understood, wholly or partly, and false when it is not understood, the parse or its proposals
 * are refused, or there is nothing to teach.
 */
export async function teach(text: string, origin: InputOrigin = 'text'): Promise<boolean> {
  text = text.trim();
  const co = store.s.activeCompany;
  if (!text || !co || !co.sid) return false;
  const end = beginProcessing();
  try {
    return await parseAndPropose({ companyId: co.sid, text, origin, sessionId: teachSessionId(co.sid) });
  } finally {
    end();
  }
}

/** Teaches the active company one stored sentence of a document import. */
async function teachSentence(importRef: ImportRef): Promise<void> {
  const co = store.s.activeCompany;
  if (!co || !co.sid) return;
  await parseAndPropose({ companyId: co.sid, importRef, sessionId: teachSessionId(co.sid) });
}

/** The longest spoken sentence one request carries, in characters, as the API allows for `speech`. */
const SPEECH_MAX_CHARS = 4000;
/** How long a spoken sentence's parse may take before it is given up, a little above the API's 45 s. */
export const SPEECH_PARSE_TIMEOUT_MS = 50_000;

/** One recording of the teach bar microphone. */
export interface SpeechStream {
  /** Queues one finished spoken sentence for the parser. */
  sentence(text: string): void;
  /** Resolves once every queued sentence is parsed and proposed. */
  settled(): Promise<void>;
}

/** The end of the spoken-sentence queue, shared by every recording so one parse is in flight at most. */
let speechTail: Promise<void> = Promise.resolve();
/** True from a `429` refusal of a spoken sentence until one is parsed again; its toast shows once. */
let speechRateLimited = false;

/**
 * Opens a recording for the active company. Each finished sentence joins one queue shared by all
 * recordings and is parsed as `speech` in the company's teach session, one request at a time: the
 * next sentence goes out once the previous one is answered (or refused) and its drafts are
 * proposed, so its back-references resolve through the stored session turn and the proposals it
 * builds on. Queueing never blocks listening.
 */
export function speechStream(): SpeechStream {
  const co = store.s.activeCompany;
  const companyId = co?.sid;
  const sessionId = companyId ? teachSessionId(companyId) : '';
  return {
    sentence(text) {
      if (!companyId) return;
      for (const piece of speechPieces(text)) {
        const end = beginProcessing();
        speechTail = speechTail
          .then(() => teachSpoken({ companyId, text: piece, origin: 'speech', sessionId }))
          .catch(showSpeechRefusal)
          .finally(end);
      }
    },
    settled: () => speechTail,
  };
}

/**
 * Parses and proposes one spoken sentence. A parse with no answer within the timeout is refused so
 * the queue moves on. A `429` shows one toast for the whole run of refusals, holds the queue for
 * its `Retry-After` and sends the sentence once more; the sentences after it follow.
 */
async function teachSpoken(request: TeachRequest): Promise<void> {
  for (let attempt = 0; ; attempt++) {
    let result: TeachResult;
    try {
      result = await withTimeout(api.teachParse(request), SPEECH_PARSE_TIMEOUT_MS);
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 429)) {
        showSpeechRefusal(err);
        return;
      }
      if (!speechRateLimited) store.refused(err);
      speechRateLimited = true;
      if (attempt > 0) return;
      await new Promise((r) => setTimeout(r, (err.retryAfter ?? 0) * 1000));
      continue;
    }
    speechRateLimited = false;
    await propose(result);
    return;
  }
}

/** Shows why a spoken sentence was not taught; a failure that is not an API refusal shows its message, so the queue never stops. */
function showSpeechRefusal(err: unknown): void {
  if (err instanceof ApiError) store.refused(err);
  else store.toast2('Refused', err instanceof Error ? err.message : String(err));
}

/** The promise's outcome, or a refusal when it takes longer than `ms`. */
function withTimeout<R>(promise: Promise<R>, ms: number): Promise<R> {
  return new Promise<R>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('The model did not answer in time')), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (err) => {
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}

/** A spoken sentence trimmed and, past the API's limit, cut at its last space before the limit. */
function speechPieces(text: string): string[] {
  const pieces: string[] = [];
  let rest = text.trim();
  while (rest.length > SPEECH_MAX_CHARS) {
    const space = rest.lastIndexOf(' ', SPEECH_MAX_CHARS);
    const cut = space > 0 ? space : SPEECH_MAX_CHARS;
    pieces.push(rest.slice(0, cut).trim());
    rest = rest.slice(cut).trim();
  }
  if (rest) pieces.push(rest);
  return pieces;
}

/** Parses and proposes one sentence; true when it is understood and its proposals are accepted. */
async function parseAndPropose(request: TeachRequest): Promise<boolean> {
  const result = await parse(request);
  return result ? propose(result) : false;
}

/** Parses one sentence; a refusal is shown and yields null. */
async function parse(request: TeachRequest): Promise<TeachResult | null> {
  try {
    return await api.teachParse(request);
  } catch (err) {
    store.refused(err);
    return null;
  }
}

/**
 * Proposes a parse's drafts and captions its outcome; true when the sentence is understood and
 * its batch, if any, is accepted.
 */
async function propose(result: TeachResult): Promise<boolean> {
  // All drafts of one parse leave as one all-or-nothing batch.
  const accepted = result.drafts.length
    ? await submitBatch(result.drafts.map(withSeed), result.parseId ?? null)
    : true;
  if (result.outcome === 'understood') {
    const n = result.statements?.length ?? result.drafts.length;
    store.caption(`Understood ${n === 1 ? 'one statement' : n + ' statements'}`, result.caption);
    return accepted;
  }
  if (result.outcome === 'partly_understood') {
    store.caption('Partly understood', result.caption);
    return accepted;
  }
  store.caption('Not understood', result.caption);
  return false;
}

/** The refusals of a batch that name a fact the model already holds. */
const DUPLICATE_CODES = new Set(['duplicate_label', 'duplicate_relation']);

/** Submits one parse's drafts; a batch refused for the proposal budget is retried whole once
 * after its `Retry-After` when that is short, never split. A batch refused because a draft
 * restates a fact already in the model is sent once more without the drafts the canvas shows
 * as already there, so the new facts of the parse are still proposed; a toast names what was
 * left out. Resolves false when the batch ends refused. `parseId` names the parse the drafts
 * came from, so the API can link the proposals to it for usage learning. */
async function submitBatch(drafts: ProposalDraft[], parseId: string | null): Promise<boolean> {
  try {
    await api.createProposalBatch(drafts, parseId);
    return true;
  } catch (err) {
    if (err instanceof ApiError && err.status === 409 && DUPLICATE_CODES.has(err.problem.code)) {
      const plan = withoutKnown(drafts);
      if (!plan.fresh.length || !plan.known.length) {
        store.refused(err);
        return false;
      }
      try {
        await api.createProposalBatch(plan.fresh, parseId);
      } catch (e) {
        store.refused(e);
        return false;
      }
      store.toast2('Already there', leftOutText(plan));
      return true;
    }
    const wait = err instanceof ApiError && err.status === 429 ? err.retryAfter : null;
    if (wait === null || wait > BATCH_RETRY_MAX_S) {
      store.refused(err);
      return false;
    }
    await new Promise((r) => setTimeout(r, wait * 1000));
    return api.createProposalBatch(drafts).then(
      () => true,
      (e) => {
        store.refused(e);
        return false;
      },
    );
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
    const via = d.type === 'concept' || d.type === 'spec' ? key(d.parentLabel) : d.type === 'attr' ? key(d.conceptLabel) : undefined;
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
    if (draft.type === 'attr' && via && replaced.get(via)?.sid) {
      const { conceptLabel: _, companyId: __, ...rest } = draft;
      draft = { ...rest, conceptId: replaced.get(via)!.sid! };
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

/** A draft's name for the toast: a concept's label, a relation's words, or an attribute and its value. */
function draftName(d: ProposalDraft): string {
  if (d.type === 'concept' || d.type === 'spec') return d.label;
  if (d.type === 'relation') {
    const a = bySid(store.s, d.aId)?.label ?? d.aLabel ?? '',
      b = bySid(store.s, d.bId)?.label ?? d.bLabel ?? '';
    return `${a} ${normaliseAction(d.action)} ${b}`.trim();
  }
  if (d.type === 'attr') {
    const holder = bySid(store.s, d.conceptId)?.label ?? d.conceptLabel ?? '';
    return `${holder} ${d.name}: ${d.value ?? d.col ?? ''}`.trim();
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

/** The import caption's note on the text pieces the API left out, empty when there are none. */
export function skippedText(skipped: number): string {
  if (!(skipped > 0)) return '';
  return ` ${skipped} short fragment${skipped === 1 ? '' : 's'} skipped.`;
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
  if (mode === 'ontology') return importOntology(file);
  store.ui.importing = true;
  const end = beginProcessing();
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
      `${imported.fileName}: ${sents.length} sentences read, ${added} proposal${added === 1 ? '' : 's'} waiting for approval on the right.${skippedText(imported.skipped)}`,
    );
  } catch (err) {
    const reason = err instanceof ApiError ? err.problem.detail || err.problem.title : (err as Error).message;
    store.caption('Import failed', `${file.name} could not be read (${reason}). Text, Markdown, CSV, Word and PDF are supported.`);
  } finally {
    store.ui.importing = false;
    end();
  }
}
