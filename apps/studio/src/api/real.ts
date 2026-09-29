/**
 * Wiring of the Studio to a real Ontaix API.
 *
 * Live events: the API does not serve the WebSocket hub yet, so each successful write replays
 * its response on the live-event bus as the envelope the hub will send (a proposal with its
 * artefacts, a decision with its cascade). Bulk runs answer with counts only, so they are
 * followed by `snapshot.required`, which reloads `GET /scene`.
 *
 * Settings, appearance and view-state writes already tolerate a refusal at their call sites.
 * Source state changes (enable, disable, refresh) answer with the source only, so they are
 * followed by `snapshot.required` for the freshness of what the source feeds.
 */
import { nowDate } from '../runtime/clock';
import { api } from './client';
import { liveEvents, type EventType } from './events';
import type { Actor, DecisionResult, Proposal } from './types';

const SYSTEM: Actor = { kind: 'system' };

let sequence = 0;

export function connectRealApi(): void {
  const raw = { ...api };

  api.createProposal = async (draft) => {
    const p = await raw.createProposal(draft);
    created(p);
    return p;
  };
  api.createProposalBatch = async (drafts) => {
    const ps = await raw.createProposalBatch(drafts);
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
  api.approveBranch = async (id) => resync(await raw.approveBranch(id));
  api.proposeExpansion = async (id, indexes) => {
    const ps = await raw.proposeExpansion(id, indexes);
    for (const p of ps) created(p);
    return ps;
  };
  api.proposeDocumentExtraction = async (id, indexes) => {
    const ps = await raw.proposeDocumentExtraction(id, indexes);
    for (const p of ps) created(p);
    return ps;
  };
  api.rejectAll = async () => resync(await raw.rejectAll());
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
  api.proposeRemoveSource = async (id) => {
    const p = await raw.proposeRemoveSource(id);
    created(p);
    return p;
  };
  api.proposeUnbind = async (id) => {
    const p = await raw.proposeUnbind(id);
    created(p);
    return p;
  };
  api.proposeRemoveCompany = async (id) => {
    const p = await raw.proposeRemoveCompany(id);
    created(p);
    return p;
  };
  api.updateSource = async (id, patch) => {
    const src = await raw.updateSource(id, patch);
    emit('source.changed', SYSTEM, { source: src, bindings: [] });
    return src;
  };
  api.enableSource = async (id) => resync(await raw.enableSource(id));
  api.disableSource = async (id) => resync(await raw.disableSource(id));
  api.refreshAllSources = async () => resync(await raw.refreshAllSources());
  api.disableCrossCompany = async (confirmation) => {
    const res = await raw.disableCrossCompany(confirmation);
    emit('settings.changed', SYSTEM, { settings: res.settings });
    return resync(res);
  };
  api.patchSettings = async (patch) => {
    const settings = await raw.patchSettings(patch);
    emit('settings.changed', SYSTEM, { settings });
    return settings;
  };
  api.patchAppearance = async (patch) => {
    const appearance = await raw.patchAppearance(patch);
    emit('appearance.changed', SYSTEM, { appearance });
    return appearance;
  };
  api.resetAppearance = async () => {
    const appearance = await raw.resetAppearance();
    emit('appearance.changed', SYSTEM, { appearance });
    return appearance;
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
