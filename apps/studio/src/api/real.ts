/**
 * Wiring of the Studio to a real Ontaix API.
 *
 * Live events: the API does not serve the WebSocket hub yet, so each successful write replays
 * its response on the live-event bus as the envelope the hub will send (a proposal with its
 * artefacts, a decision with its cascade). Bulk runs answer with counts only, so they are
 * followed by `snapshot.required`, which reloads `GET /scene`.
 *
 * Drafts: the contract accepts a concept or spec parent by id or by label, never both; the
 * story sends both, so the id wins and an empty id gives way to the label.
 *
 * Local fallbacks, clearly scoped to routes the API answers with 404 today:
 *   POST /teach/parse   parsed in the browser (./local-teach)
 *   POST /demo/reset    reloads the scene instead of rebuilding the home company
 * Settings, appearance and view-state writes already tolerate a refusal at their call sites.
 */
import { nowDate } from '../runtime/clock';
import { store } from '../store/store';
import { api } from './client';
import { liveEvents, type EventType } from './events';
import { localTeachParse } from './local-teach';
import { ApiError, type Actor, type DecisionResult, type Proposal, type ProposalDraft } from './types';

const SYSTEM: Actor = { kind: 'system' };

let sequence = 0;

export function connectRealApi(): void {
  const raw = { ...api };

  api.createProposal = async (draft) => {
    const p = await raw.createProposal(contractDraft(draft));
    created(p);
    return p;
  };
  api.createProposalBatch = async (drafts) => {
    const ps = await raw.createProposalBatch(drafts.map(contractDraft));
    for (const p of ps) created(p);
    return ps;
  };
  api.approve = async (id) => decided(await raw.approve(id));
  api.secondApprove = async (id) => decided(await raw.secondApprove(id));
  api.reject = async (id, reason) => {
    const res = await raw.reject(id, reason);
    emit('proposal.rejected', res.proposal.proposer, { ...res, audit: undefined });
    return res;
  };
  api.approveAll = async () => resync(await raw.approveAll());
  api.rejectAll = async () => resync(await raw.rejectAll());
  api.finaliseAll = async () => resync(await raw.finaliseAll());
  api.createCompany = async (body) => {
    const res = await raw.createCompany(body);
    emit('company.created', SYSTEM, { company: res.company, root: res.root });
    for (const p of res.proposals) created(p);
    return res;
  };
  api.updateDomainProduct = async (id, patch) => {
    const dp = await raw.updateDomainProduct(id, patch);
    emit('domain_product.changed', SYSTEM, { domainProduct: dp });
    return dp;
  };
  api.teachParse = async (body) => {
    try {
      return await raw.teachParse(body);
    } catch (err) {
      if (!isMissingRoute(err)) throw err;
      return localTeachParse(store.s, body);
    }
  };
  api.demoReset = async () => {
    try {
      return await raw.demoReset();
    } catch (err) {
      if (!isMissingRoute(err)) throw err;
      return await raw.getScene();
    }
  };
}

function created(p: Proposal): void {
  emit('proposal.created', p.proposer, { proposal: p, artefacts: p.artefacts || {}, cascaded: [] });
}

function decided(res: DecisionResult): DecisionResult {
  const type: EventType = res.proposal.state === 'approved' ? 'proposal.approved' : 'proposal.half_approved';
  emit(type, res.proposal.proposer, { ...res, audit: undefined });
  return res;
}

function resync<R>(res: R): R {
  emit('snapshot.required', SYSTEM, {});
  return res;
}

function emit(type: EventType, actor: Actor, payload: Record<string, unknown>): void {
  sequence += 1;
  liveEvents.emit({
    id: `http-${sequence}`,
    type,
    occurredAt: nowDate().toISOString(),
    tenantId: '',
    sequence,
    actor,
    bulk: false,
    payload,
  });
}

function contractDraft(draft: ProposalDraft): ProposalDraft {
  if (draft.type !== 'concept' && draft.type !== 'spec') return draft;
  const { parentId, parentLabel, ...rest } = draft;
  return (parentId ? { ...rest, parentId } : { ...rest, parentLabel }) as ProposalDraft;
}

/** A bare 404 `not_found` (no resource-specific code): the route does not exist on this API. */
function isMissingRoute(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404 && err.problem.code === 'not_found';
}
