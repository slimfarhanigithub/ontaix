/**
 * In-browser mock of the Ontaix API over an in-memory store seeded from the reference
 * constants. It answers the routes the Studio canvas uses with the shapes of
 * contracts/openapi.yaml and publishes every change on the live event bus, the way the real
 * API does over the WebSocket. Proposal text, readiness and side effects are the server-side
 * port of the reference's `pConcept`, `pSpec`, `pRelation`, `pSource`, `pBind`, `pAttr`,
 * `approve`, `reject` and `afterApply` (reference lines 573-607).
 */
import { DEFAULT_BRASS, DOMAIN_R, DOMAIN_TEMPLATES, C, NEUTRAL } from '../../canvas/constants';
import { demoScenes, SCENES } from '../../demo/scenes';
import { contentWords, domainPrefix, singular, title, understand } from '../../nl/parser';
import { nowDate } from '../../runtime/clock';
import { random } from '../../runtime/rng';
import { escapeHtml } from '../../shell/sanitize';
import { mixedRelationEnd } from '../drafts';
import { liveEvents, type EventBus, type EventType } from '../events';
import type * as T from '../types';
import { ATTR, CATALOG, generic, HOME_COMPANY, RECORDS, SEED, type AttrSpec } from './seed';

interface MCompany {
  id: string;
  key: string;
  name: string;
  sub: string;
  position: number;
  rootId: string;
  domains: MDomain[];
}

interface MDomain {
  id: string;
  companyId: string;
  key: T.DomainKey;
  name: string;
  owner: string;
  templateColor: string;
  revision: number;
  hidden: boolean;
}

interface MAttr {
  id: string;
  conceptId: string;
  sourceId: string | null;
  name: string;
  type: T.AttributeType;
  col: string;
  fill: number;
  state: 'proposed' | 'approved';
}

interface MBinding {
  id: string;
  sourceId: string;
  conceptId: string;
  records: number;
  fresh: string;
  pending: boolean;
}

interface MConcept {
  id: string;
  companyId: string;
  kind: 'root' | 'concept';
  label: string;
  sub: string;
  domainKey: T.DomainKey | null;
  rule: string | null;
  pending: boolean;
  conflict: boolean;
  parentId: string | null;
  birthRelationId: string | null;
  bornAt: string;
  x: number;
  y: number;
  pinned: boolean;
  dyingAt: string | null;
  bound: MBinding | null;
  attributes: MAttr[];
}

interface MSource {
  id: string;
  companyId: string;
  label: string;
  kindText: string;
  connectorCode: string | null;
  host: string | null;
  scope: string | null;
  auth: T.SourceAuth | null;
  refresh: T.RefreshInterval;
  anchorIndex: number;
  disabled: boolean;
  pending: boolean;
  x: number;
  y: number;
  pinned: boolean;
  dyingAt: string | null;
}

interface MRelation {
  id: string;
  aId: string;
  bId: string;
  kind: T.RelationKind;
  label: string;
  rest: number;
  seed: number;
  pending: boolean;
  dyingAt: string | null;
}

interface MProposal {
  id: string;
  type: T.ProposalType;
  changeKind: T.ChangeKind | null;
  state: T.ProposalState;
  title: string;
  heading: string;
  color: string;
  companyId: string | null;
  domainId: string | null;
  parentLabel: string | null;
  deps: string[];
  ready: () => boolean;
  waitFor: string | null;
  html: string;
  why: string;
  caption: string | null;
  conceptId: string | null;
  relationId: string | null;
  relationIds: string[];
  sourceId: string | null;
  bindingIds: string[];
  attributeId: string | null;
  createdAt: string;
  decidedAt: string | null;
  second: boolean;
  apply?: () => void;
  onReject?: () => void;
}

export interface MockResponse {
  status: number;
  body: unknown;
}

export interface MockServer {
  handle(method: string, path: string, body?: unknown): MockResponse;
}

class Refusal extends Error {
  constructor(
    public status: number,
    public code: string,
    public detail: string,
  ) {
    super(detail);
  }
}

const TENANT_ID = '00000000-0000-4000-8000-00000000000a';
const ACTOR: T.Actor = { kind: 'user', id: '00000000-0000-4000-8000-0000000000a1', name: 'Owner' };
const KIND_HEADING: Record<T.ProposalType, string> = {
  concept: 'New concept',
  spec: 'Specialisation',
  relation: 'Relation',
  change: 'Change',
  source: 'Data source',
  bind: 'Binding',
  attr: 'Attribute',
};

export function createMockServer(bus: EventBus = liveEvents): MockServer {
  let counter = 0;
  const uuid = () => `00000000-0000-4000-8000-${String(++counter).padStart(12, '0')}`;
  const iso = () => nowDate().toISOString();
  /** Label text as it may appear inside proposal html: escaped, so markup only ever comes from the builders. */
  const e = escapeHtml;

  let companies: MCompany[] = [];
  let concepts: MConcept[] = [];
  let sources: MSource[] = [];
  let relations: MRelation[] = [];
  let bindings: MBinding[] = [];
  let proposals: MProposal[] = [];
  let audit: T.AuditEntry[] = [];
  let sequence = 0;
  let sceneIdx = 0;
  let coverage = false;
  const settings: T.Settings = {
    voice: true,
    importDocs: true,
    liveTeaching: true,
    everyoneTeaches: false,
    approvalRequired: true,
    twoApprovers: false,
    autoAttrs: false,
    notifyOwners: true,
    multiCompany: true,
    crossCompany: true,
    animations: true,
    coverageDefault: false,
    legend: true,
    readOnlyConnectors: true,
    refresh: '15 min',
    agentAccess: true,
    costCap: true,
    demoStory: true,
  };
  const appearance = { theme: 'dark' as 'dark' | 'light', colors: {} as Record<string, string>, accent: '#3fb8a9', source: DEFAULT_BRASS };

  const colourOf = (d: MDomain) => appearance.colors[d.key] || d.templateColor;
  const companyOf = (id: string) => companies.find((c) => c.id === id) || null;
  const conceptById = (id: string | null | undefined) => concepts.find((c) => c.id === id) || null;
  const sourceById = (id: string | null | undefined) => sources.find((c) => c.id === id) || null;
  const relationById = (id: string | null | undefined) => relations.find((c) => c.id === id) || null;
  const domainById = (id: string | null) => companies.flatMap((c) => c.domains).find((d) => d.id === id) || null;
  const domainOfConcept = (c: MConcept) =>
    c.domainKey ? companyOf(c.companyId)?.domains.find((d) => d.key === c.domainKey) || null : null;
  const domainByKey = (companyId: string, key: string | null | undefined) =>
    companyOf(companyId)?.domains.find((d) => d.key === key) || null;
  /** A living concept by label inside a company, the reference's `find`. */
  const findConcept = (label: string, companyId: string) =>
    concepts.find((n) => n.label.toLowerCase() === label.toLowerCase() && n.companyId === companyId && !n.dyingAt) ||
    null;
  const open = () => proposals.filter((p) => p.state === 'pending' || p.state === 'half_approved');

  function addAudit(
    kind: string,
    what: string,
    ok: boolean,
    proposalId: string | null = null,
    companyIds: string[] = [],
  ): T.AuditEntry {
    const e: T.AuditEntry = { id: audit.length + 1, at: iso(), actor: ACTOR, kind, what, ok, proposalId, companyIds };
    audit.unshift(e);
    if (audit.length > 400) audit.pop();
    return e;
  }

  function emit(type: EventType, payload: Record<string, unknown>, bulk = false): void {
    bus.emit({ id: uuid(), type, occurredAt: iso(), tenantId: TENANT_ID, sequence: ++sequence, actor: ACTOR, bulk, payload });
  }

  // ------------------------------------------------------------ projections

  const toBinding = (b: MBinding): T.Binding => ({
    id: b.id,
    sourceId: b.sourceId,
    sourceLabel: sourceById(b.sourceId)?.label ?? '',
    conceptId: b.conceptId,
    records: b.records,
    fresh: b.fresh,
    pending: b.pending,
  });

  const toAttribute = (a: MAttr): T.Attribute => ({ ...a });

  const toConcept = (c: MConcept): T.Concept => {
    const d = domainOfConcept(c);
    return {
      id: c.id,
      companyId: c.companyId,
      kind: c.kind,
      label: c.label,
      sub: c.sub,
      domainProductId: d ? d.id : null,
      domainKey: c.domainKey,
      color: c.kind === 'root' ? C.root : d ? colourOf(d) : NEUTRAL,
      rule: c.rule,
      pending: c.pending,
      conflict: c.conflict,
      parentId: c.parentId,
      birthRelationId: c.birthRelationId,
      bornAt: c.bornAt,
      x: c.x,
      y: c.y,
      pinned: c.pinned,
      dyingAt: c.dyingAt,
      bound: c.bound ? toBinding(c.bound) : null,
      attributes: c.attributes.map(toAttribute),
      relationCount: relations.filter((l) => (l.aId === c.id || l.bId === c.id) && !l.dyingAt).length,
      state: c.pending ? 'awaiting approval' : /certified/.test(c.sub) ? 'certified' : 'approved',
      isSpecialisation: relations.some((l) => l.aId === c.id && l.kind === 'isa'),
    };
  };

  const toSource = (n: MSource): T.Source => {
    const b = bindings.filter((x) => x.sourceId === n.id && !x.pending);
    const rec = b.reduce((a, x) => a + x.records, 0);
    return {
      id: n.id,
      companyId: n.companyId,
      label: n.label,
      kindText: n.kindText,
      connectorCode: n.connectorCode,
      host: n.host,
      scope: n.scope,
      auth: n.auth,
      refresh: n.refresh,
      anchorIndex: n.anchorIndex,
      disabled: n.disabled,
      pending: n.pending,
      x: n.x,
      y: n.y,
      pinned: n.pinned,
      dyingAt: n.dyingAt,
      feeds: b.length,
      records: rec || null,
      state: n.pending ? 'awaiting approval' : n.disabled ? 'disabled' : 'connected',
    };
  };

  const toRelation = (l: MRelation): T.Relation => {
    const a = conceptById(l.aId),
      b = conceptById(l.bId);
    const ad = a ? domainOfConcept(a) : null,
      bd = b ? domainOfConcept(b) : null;
    return {
      id: l.id,
      aId: l.aId,
      bId: l.bId,
      aLabel: a?.label ?? '',
      bLabel: b?.label ?? '',
      kind: l.kind,
      label: l.label,
      rest: l.rest,
      seed: l.seed,
      pending: l.pending,
      dyingAt: l.dyingAt,
      companyIds: [...new Set([a?.companyId, b?.companyId].filter((x): x is string => !!x))],
      scope: ad === bd ? (ad ? ad.name : 'company') : `${ad ? ad.name : 'company'} → ${bd ? bd.name : 'company'}`,
      state: l.pending ? 'awaiting approval' : 'approved',
    };
  };

  const toDomain = (d: MDomain): T.DomainProduct => {
    const members = concepts.filter((n) => n.domainKey === d.key && n.companyId === d.companyId && !n.dyingAt);
    return {
      id: d.id,
      companyId: d.companyId,
      key: d.key,
      name: d.name,
      owner: d.owner,
      color: colourOf(d),
      revision: d.revision,
      version: `v1.${d.revision}`,
      hidden: d.hidden,
      counts: {
        members: members.length,
        pending: members.filter((n) => n.pending).length,
        bound: members.filter((n) => n.bound).length,
      },
    };
  };

  const toCompany = (c: MCompany): T.Company => {
    const mine = concepts.filter((n) => n.companyId === c.id && n.kind === 'concept' && !n.dyingAt);
    const bound = mine.filter((n) => n.bound).length;
    return {
      id: c.id,
      key: c.key,
      name: c.name,
      sub: c.sub,
      position: c.position,
      isHome: c.position === 0,
      rootId: c.rootId,
      domainProducts: c.domains.map(toDomain),
      counts: {
        concepts: mine.length,
        sources: sources.filter((n) => n.companyId === c.id && !n.dyingAt).length,
        equivalences: relations.filter(
          (l) => l.kind === 'same' && [conceptById(l.aId)?.companyId, conceptById(l.bId)?.companyId].includes(c.id),
        ).length,
        bound,
        percentBound: mine.length ? Math.round((bound / mine.length) * 100) : 0,
        domainsWithCells: c.domains.filter((d) => mine.some((n) => n.domainKey === d.key)).length,
      },
      dyingAt: null,
    };
  };

  const artefactsOf = (p: MProposal): T.Artefacts => {
    const cs = [p.conceptId].map(conceptById).filter((x): x is MConcept => !!x);
    const rs = [p.relationId, ...p.relationIds].map(relationById).filter((x): x is MRelation => !!x);
    const ss = [p.sourceId].map(sourceById).filter((x): x is MSource => !!x);
    const bs = p.bindingIds.map((id) => bindings.find((b) => b.id === id)).filter((x): x is MBinding => !!x);
    const as = p.attributeId ? concepts.flatMap((c) => c.attributes).filter((a) => a.id === p.attributeId) : [];
    const ds = p.domainId ? [domainById(p.domainId)].filter((x): x is MDomain => !!x) : [];
    return {
      concepts: cs.map(toConcept),
      relations: rs.map(toRelation),
      sources: ss.map(toSource),
      bindings: bs.map(toBinding),
      attributes: as.map(toAttribute),
      domainProducts: ds.map(toDomain),
    };
  };

  const toProposal = (p: MProposal): T.Proposal => ({
    id: p.id,
    type: p.type,
    changeKind: p.changeKind,
    state: p.state,
    title: p.title,
    heading: p.heading,
    color: p.color,
    companyId: p.companyId,
    domainProductId: p.domainId,
    parentLabel: p.parentLabel,
    deps: p.deps,
    ready: p.ready(),
    waitFor: p.waitFor,
    html: p.html,
    why: p.why || null,
    caption: p.caption,
    conceptId: p.conceptId,
    relationId: p.relationId,
    relationIds: p.relationIds,
    sourceId: p.sourceId,
    bindingIds: p.bindingIds,
    attributeId: p.attributeId,
    proposer: ACTOR,
    approvals: [],
    createdAt: p.createdAt,
    decidedAt: p.decidedAt,
    artefacts: artefactsOf(p),
  });

  const toAppearance = (): T.Appearance => ({
    theme: appearance.theme,
    colors: Object.fromEntries(DOMAIN_TEMPLATES.map((t) => [t.key, appearance.colors[t.key] || t.color])),
    accent: appearance.accent,
    source: appearance.source,
    defaults: { colors: Object.fromEntries(DOMAIN_TEMPLATES.map((t) => [t.key, t.color])), accent: '#3fb8a9', source: DEFAULT_BRASS },
  });

  const toScene = (): T.Scene => ({
    sequence,
    serverTime: iso(),
    companies: companies.map(toCompany),
    nodes: [...concepts.filter((c) => !c.dyingAt).map(toConcept), ...sources.filter((n) => !n.dyingAt).map(toSource)],
    links: [...relations.filter((l) => !l.dyingAt).map(toRelation), ...bindings.map(toBinding)],
    proposals: open().map(toProposal),
    settings: { ...settings },
    appearance: toAppearance(),
    viewState: { coverage, sceneIdx },
    connectors: CATALOG.map(([code, name, category, scopeText]) => ({ code, name, category, scopeText })),
    demoStory: { enabled: settings.demoStory, sceneIdx, sceneCount: demoScenes().length },
  });

  // ------------------------------------------------------------ model helpers

  /** A relation row; the bend is the client's draw when the draft carried one, else drawn here. */
  function newRelation(a: MConcept, b: MConcept, kind: T.RelationKind, rest: number, label: string, seed?: number): MRelation {
    const bend = typeof seed === 'number' && seed >= 0 && seed <= 1 ? seed : random();
    const l: MRelation = { id: uuid(), aId: a.id, bId: b.id, kind, label, rest, seed: bend, pending: false, dyingAt: null };
    relations.push(l);
    return l;
  }

  function newProposal(p: Omit<MProposal, 'id' | 'state' | 'createdAt' | 'decidedAt' | 'second'>): MProposal {
    const full: MProposal = { ...p, id: uuid(), state: 'pending', createdAt: iso(), decidedAt: null, second: false };
    proposals.push(full);
    return full;
  }

  function addCompany(name: string, sub: string): MCompany {
    const id = uuid();
    const c: MCompany = {
      id,
      key: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
      name,
      sub,
      position: companies.length,
      rootId: '',
      domains: DOMAIN_TEMPLATES.map((t) => ({
        id: uuid(),
        companyId: id,
        key: t.key,
        name: t.name,
        owner: t.owner,
        templateColor: t.color,
        revision: 0,
        hidden: false,
      })),
    };
    const root: MConcept = {
      id: uuid(),
      companyId: id,
      kind: 'root',
      label: name,
      sub: sub || '',
      domainKey: null,
      rule: null,
      pending: false,
      conflict: false,
      parentId: null,
      birthRelationId: null,
      bornAt: iso(),
      x: 0,
      y: 0,
      pinned: false,
      dyingAt: null,
      bound: null,
      attributes: [],
    };
    c.rootId = root.id;
    companies.push(c);
    concepts.push(root);
    return c;
  }

  /** Walks birth links upward from `n`; true when `anc` is reached. */
  function descends(n: MConcept, anc: MConcept): boolean {
    let c: MConcept | null = n;
    for (let k = 0; k < 50 && c; k++) {
      const cur: MConcept = c;
      const l = relations.find(
        (x) => (x.kind === 'isa' && x.aId === cur.id) || (x.kind === 'rel' && x.bId === cur.id && x.aId !== cur.id),
      );
      if (!l) return false;
      c = conceptById(l.kind === 'isa' ? l.bId : l.aId);
      if (c === anc) return true;
    }
    return false;
  }

  // ------------------------------------------------------------ proposal builders

  function pConcept(host: MConcept, label: string, domainKey: string | null, pred: string, cap: string | undefined, reverse: boolean, seed?: number): MProposal {
    const dom = domainByKey(host.companyId, domainKey) || domainOfConcept(host);
    const concept: MConcept = {
      id: uuid(),
      companyId: host.companyId,
      kind: 'concept',
      label,
      sub: '',
      domainKey: dom ? dom.key : null,
      rule: null,
      pending: true,
      conflict: false,
      parentId: host.id,
      birthRelationId: null,
      bornAt: iso(),
      x: host.x,
      y: host.y,
      pinned: false,
      dyingAt: null,
      bound: null,
      attributes: [],
    };
    concepts.push(concept);
    const cross = host.domainKey !== concept.domainKey;
    const rel = reverse
      ? newRelation(concept, host, 'rel', cross ? 330 : 220, pred, seed)
      : newRelation(host, concept, 'rel', cross ? 330 : 220, pred, seed);
    rel.pending = true;
    concept.birthRelationId = rel.id;
    const parentLabel = host.label;
    return newProposal({
      type: 'concept',
      changeKind: null,
      title: label,
      heading: KIND_HEADING.concept + (dom ? ` · ${dom.name}` : ''),
      color: dom ? colourOf(dom) : NEUTRAL,
      companyId: host.companyId,
      domainId: dom ? dom.id : null,
      parentLabel,
      deps: [parentLabel],
      ready: () => {
        const n = findConcept(parentLabel, host.companyId);
        return !!n && !n.pending && !n.dyingAt;
      },
      waitFor: parentLabel,
      html: reverse
        ? `<b>${e(label)}</b> <em>· ${e(label)} <b>${e(pred)}</b> ${e(parentLabel)}</em>`
        : `<b>${e(label)}</b> <em>· ${e(parentLabel)} <b>${e(pred)}</b> ${e(label)}</em>`,
      why: dom ? `domain product: ${dom.name}` : '',
      caption: cap ?? null,
      conceptId: concept.id,
      relationId: rel.id,
      relationIds: [],
      sourceId: null,
      bindingIds: [],
      attributeId: null,
    });
  }

  function pSpec(host: MConcept, label: string, rule: string, cap: string | undefined, domainKey: string | null, seed?: number): MProposal {
    const dom = domainByKey(host.companyId, domainKey) || domainOfConcept(host);
    const concept: MConcept = {
      id: uuid(),
      companyId: host.companyId,
      kind: 'concept',
      label,
      sub: '',
      domainKey: dom ? dom.key : null,
      rule: rule || null,
      pending: true,
      conflict: false,
      parentId: host.id,
      birthRelationId: null,
      bornAt: iso(),
      x: host.x,
      y: host.y,
      pinned: false,
      dyingAt: null,
      bound: null,
      attributes: [],
    };
    concepts.push(concept);
    const cross = host.domainKey !== concept.domainKey;
    const rel = newRelation(concept, host, 'isa', cross ? 300 : 170, 'is a', seed);
    rel.pending = true;
    concept.birthRelationId = rel.id;
    const parentLabel = host.label;
    const hostDom = domainOfConcept(host);
    return newProposal({
      type: 'spec',
      changeKind: null,
      title: label,
      heading: KIND_HEADING.spec + (dom ? ` · ${dom.name}` : ''),
      color: dom ? colourOf(dom) : hostDom ? colourOf(hostDom) : C.root,
      companyId: host.companyId,
      domainId: dom ? dom.id : null,
      parentLabel,
      deps: [parentLabel],
      ready: () => {
        const n = findConcept(parentLabel, host.companyId);
        return !!n && !n.pending && !n.dyingAt;
      },
      waitFor: parentLabel,
      html: `<b>${e(label)}</b> <em>is a ${e(parentLabel)}</em>`,
      why: (rule ? `rule: ${rule}` : '') + (dom ? ` · domain product: ${dom.name}` : ''),
      caption: cap ?? null,
      conceptId: concept.id,
      relationId: rel.id,
      relationIds: [],
      sourceId: null,
      bindingIds: [],
      attributeId: null,
    });
  }

  function pRelation(a: MConcept, pred: string, b: MConcept, cap: string | undefined, seed?: number): MProposal {
    if (a.companyId !== b.companyId && !settings.crossCompany)
      throw new Refusal(409, 'cross_company_disabled', 'companies may not interact · enable it in the admin portal');
    const kind: T.RelationKind = pred === 'is a' ? 'isa' : pred === 'equivalent to' ? 'same' : 'rel';
    if (relations.some((l) => l.aId === a.id && l.bId === b.id && l.label === pred && !l.dyingAt))
      throw new Refusal(409, 'duplicate_relation', `${a.label} ${pred} ${b.label} is already in the model.`);
    const ad = domainOfConcept(a),
      bd = domainOfConcept(b);
    const cross = ad !== bd;
    const xco = a.companyId !== b.companyId;
    const aCo = companyOf(a.companyId),
      bCo = companyOf(b.companyId);
    const rel = newRelation(a, b, kind, xco ? 560 : cross ? 330 : 220, pred, seed);
    rel.pending = true;
    return newProposal({
      type: 'relation',
      changeKind: null,
      title: `${a.label} ${pred} ${b.label}`,
      heading: KIND_HEADING.relation,
      color: NEUTRAL,
      companyId: a.companyId,
      domainId: ad ? ad.id : null,
      parentLabel: null,
      deps: [a.label, b.label],
      ready: () => !a.pending && !b.pending && !a.dyingAt && !b.dyingAt,
      waitFor: `${a.label} and ${b.label}`,
      html: `${e(a.label)}${xco ? ' <em>(' + e(aCo?.name ?? '') + ')</em>' : ''} <b>${e(pred)}</b> ${e(b.label)}${xco ? ' <em>(' + e(bCo?.name ?? '') + ')</em>' : ''}`,
      why: xco
        ? `across companies: ${aCo?.name} ↔ ${bCo?.name}`
        : cross
          ? `across domain products: ${ad ? ad.name : 'company'} → ${bd ? bd.name : 'company'}`
          : `inside ${ad ? ad.name : 'the company'}`,
      caption: cap ?? null,
      conceptId: null,
      relationId: rel.id,
      relationIds: [],
      sourceId: null,
      bindingIds: [],
      attributeId: null,
    });
  }

  function pSource(company: MCompany, label: string, kindText: string, cap: string | undefined, d: Partial<T.SourceDraft> = {}): MProposal {
    const i = sources.filter((n) => n.companyId === company.id && !n.dyingAt).length;
    const a = -Math.PI / 2 + Math.PI / 9 + (i * Math.PI * 2) / 8;
    const R = DOMAIN_R + 360;
    const src: MSource = {
      id: uuid(),
      companyId: company.id,
      label,
      kindText: kindText || 'system',
      connectorCode: d.connectorCode ?? null,
      host: d.host ?? null,
      scope: d.scope ?? null,
      auth: d.auth ?? null,
      refresh: d.refresh ?? settings.refresh,
      anchorIndex: i,
      disabled: false,
      pending: true,
      x: Math.cos(a) * R,
      y: Math.sin(a) * R,
      pinned: false,
      dyingAt: null,
    };
    sources.push(src);
    return newProposal({
      type: 'source',
      changeKind: null,
      title: label,
      heading: KIND_HEADING.source,
      color: appearance.source,
      companyId: company.id,
      domainId: null,
      parentLabel: null,
      deps: [],
      ready: () => true,
      waitFor: null,
      html: `<b>${e(label)}</b> <em>· ${e(kindText)} joins ${e(company.name)} as a data source</em>`,
      why: 'systems are not concepts: they feed them',
      caption: cap || `${label} is connected. Nothing is bound to it yet.`,
      conceptId: null,
      relationId: null,
      relationIds: [],
      sourceId: src.id,
      bindingIds: [],
      attributeId: null,
    });
  }

  function pAttr(n: MConcept, a: AttrSpec, sourceId: string | null): MProposal {
    const attr: MAttr = { id: uuid(), conceptId: n.id, sourceId, name: a[0], type: a[1] as T.AttributeType, col: a[2], fill: a[3], state: 'proposed' };
    n.attributes.push(attr);
    return newProposal({
      type: 'attr',
      changeKind: null,
      title: `${n.label}.${a[0]}`,
      heading: KIND_HEADING.attr,
      color: appearance.source,
      companyId: n.companyId,
      domainId: null,
      parentLabel: null,
      deps: [],
      ready: () => true,
      waitFor: null,
      html: `<b>${e(n.label)}</b> has <b>${e(a[0])}</b> <em>· ${e(a[1])} · found in ${e(a[2])}</em>`,
      why: `${a[3]} percent filled · in the data, not yet in the model`,
      caption: `${n.label}.${a[0]} is now part of the model, read from ${a[2]}.`,
      conceptId: n.id,
      relationId: null,
      relationIds: [],
      sourceId: null,
      bindingIds: [],
      attributeId: attr.id,
      apply() {
        attr.state = 'approved';
      },
      onReject() {
        const i = n.attributes.indexOf(attr);
        if (i >= 0) n.attributes.splice(i, 1);
      },
    });
  }

  function pBind(src: MSource, targets: MConcept[], cap: string | undefined, cascade: MProposal[]): MProposal {
    const made = targets.map((n) => {
      const b: MBinding = { id: uuid(), sourceId: src.id, conceptId: n.id, records: 0, fresh: '—', pending: true };
      bindings.push(b);
      return b;
    });
    const sourceLabel = src.label;
    return newProposal({
      type: 'bind',
      changeKind: null,
      title: `Bind ${targets.length} concept${targets.length === 1 ? '' : 's'} to ${sourceLabel}`,
      heading: KIND_HEADING.bind,
      color: appearance.source,
      companyId: src.companyId,
      domainId: null,
      parentLabel: null,
      deps: [sourceLabel, ...targets.map((n) => n.label)],
      ready: () => !src.pending && targets.every((n) => !n.pending && !n.dyingAt),
      waitFor: sourceLabel,
      html: `<b>${e(sourceLabel)}</b> feeds ${targets.map((n) => '<b>' + e(n.label) + '</b>').join(', ')}`,
      why: `${targets.reduce((a, n) => a + (RECORDS[n.label] || 1200), 0).toLocaleString('en-GB')} records · attributes are read from the schema`,
      caption:
        cap ||
        `${targets.length} concept${targets.length === 1 ? ' is' : 's are'} now wired to ${sourceLabel}. Attributes found in the data appear as proposals.`,
      conceptId: null,
      relationId: null,
      relationIds: [],
      sourceId: src.id,
      bindingIds: made.map((b) => b.id),
      attributeId: null,
      apply() {
        for (const b of made) b.pending = false;
        for (const n of targets) {
          const b = made.find((x) => x.conceptId === n.id) as MBinding;
          b.records = RECORDS[n.label] || 800 + Math.floor(random() * 9000);
          b.fresh = ['2 min', '4 min', '11 min', '1 h'][Math.floor(random() * 4)];
          n.bound = b;
          const spec = ATTR[n.label] || generic(n.label);
          n.attributes = spec
            .filter((a) => a[4] !== 'new')
            .map((a) => ({ id: uuid(), conceptId: n.id, sourceId: src.id, name: a[0], type: a[1] as T.AttributeType, col: a[2], fill: a[3], state: 'approved' as const }));
          for (const a of spec.filter((a) => a[4] === 'new')) {
            const q = pAttr(n, a, src.id);
            cascade.push(q);
            if (settings.autoAttrs) approve(q, true, cascade);
          }
        }
      },
    });
  }

  function pChange(draft: T.ChangeDraft): MProposal {
    const pl = draft.payload;
    if (draft.changeKind === 'resolve_conflict') {
      const ids = pl.conflictConceptIds;
      if (!ids) throw new Refusal(422, 'missing_conflict_ids', 'conflictConceptIds is required');
      const pair = ids.map(conceptById);
      if (pair.some((c) => !c)) throw new Refusal(404, 'concept_not_found', 'a conflict concept does not exist');
      const [first] = pair as MConcept[];
      return newProposal({
        type: 'change',
        changeKind: 'resolve_conflict',
        title: 'Resolve the conflict',
        heading: KIND_HEADING.change,
        color: '#3fb8a9',
        companyId: first.companyId,
        domainId: null,
        parentLabel: null,
        deps: ['both definitions'],
        ready: () => concepts.filter((n) => n.label === 'Defective product' && !n.pending && !n.dyingAt).length >= 2,
        waitFor: 'both definitions',
        html: `Rename Production’s <b>Defective product</b> to <b>Scrapped product</b>, certify both, and declare <b>Scrapped product is a Defective product</b>`,
        why: '',
        caption:
          draft.caption ??
          'One business, two certified truths, each owned by its domain product. Quality keeps its definition, Production keeps its own name, and the model records that one is a kind of the other.',
        conceptId: null,
        relationId: null,
        relationIds: [],
        sourceId: null,
        bindingIds: [],
        attributeId: null,
        apply() {
          const both = concepts.filter((n) => n.label === 'Defective product' && !n.dyingAt);
          const q = both.find((n) => n.rule === 'failed inspection') || both[0],
            p = both.find((n) => n !== q);
          if (!q || !p) return;
          const i = relations.findIndex((l) => l.kind === 'clash');
          if (i >= 0) relations.splice(i, 1);
          q.conflict = p.conflict = false;
          q.sub = 'failed inspection · certified';
          p.label = 'Scrapped product';
          p.sub = 'scrapped · certified';
          const j = relations.findIndex((l) => l.aId === p.id && l.kind === 'isa');
          if (j >= 0) relations.splice(j, 1);
          newRelation(p, q, 'isa', 300, 'is a');
        },
      });
    }
    if (draft.changeKind === 'rename') {
      const n = conceptById(pl.conceptId);
      const name = pl.newLabel || '';
      if (!n) throw new Refusal(404, 'concept_not_found', 'concept does not exist');
      if (!name || name === n.label) throw new Refusal(422, 'same_label', 'the new label equals the current one');
      const d = domainOfConcept(n);
      return newProposal({
        type: 'change',
        changeKind: 'rename',
        title: `Rename ${n.label} to ${name}`,
        heading: KIND_HEADING.change + (d ? ` · ${d.name}` : ''),
        color: d ? colourOf(d) : C.root,
        companyId: n.companyId,
        domainId: d ? d.id : null,
        parentLabel: null,
        deps: [],
        ready: () => true,
        waitFor: null,
        html: `Rename <b>${e(n.label)}</b> to <b>${e(name)}</b>`,
        why: `${relations.filter((l) => l.aId === n.id || l.bId === n.id).length} relations keep pointing at it`,
        caption: draft.caption ?? `${n.label} is now called ${name}.`,
        conceptId: n.id,
        relationId: null,
        relationIds: [],
        sourceId: null,
        bindingIds: [],
        attributeId: null,
        apply() {
          n.label = name;
        },
      });
    }
    if (draft.changeKind === 'delete_concept') {
      const n = conceptById(pl.conceptId);
      if (!n) throw new Refusal(404, 'concept_not_found', 'concept does not exist');
      const rel = relations.filter((l) => l.aId === n.id || l.bId === n.id).length;
      const d = domainOfConcept(n);
      return newProposal({
        type: 'change',
        changeKind: 'delete_concept',
        title: `Delete ${n.label}`,
        heading: KIND_HEADING.change + (d ? ` · ${d.name}` : ''),
        color: C.conflict,
        companyId: n.companyId,
        domainId: d ? d.id : null,
        parentLabel: null,
        deps: [],
        ready: () => true,
        waitFor: null,
        html: `Delete <b>${e(n.label)}</b> and its ${rel} relation${rel === 1 ? '' : 's'}`,
        why: 'specialisations of it are deleted too',
        caption: draft.caption ?? `${n.label} was removed from the model.`,
        conceptId: n.id,
        relationId: null,
        relationIds: [],
        sourceId: null,
        bindingIds: [],
        attributeId: null,
        apply() {
          const t = iso();
          n.dyingAt = t;
          for (const q of concepts) if (q !== n && descends(q, n)) q.dyingAt = t;
        },
      });
    }
    if (draft.changeKind === 'remove_relation' || draft.changeKind === 'edit_relation') {
      const link = relationById(pl.relationId);
      if (!link) throw new Refusal(404, 'relation_not_found', 'relation does not exist');
      const a = conceptById(link.aId) as MConcept,
        b = conceptById(link.bId) as MConcept;
      const ad = domainOfConcept(a);
      if (draft.changeKind === 'remove_relation')
        return newProposal({
          type: 'change',
          changeKind: 'remove_relation',
          title: `Remove ${a.label} ${link.label} ${b.label}`,
          heading: KIND_HEADING.change + (ad ? ` · ${ad.name}` : ''),
          color: C.conflict,
          companyId: a.companyId,
          domainId: ad ? ad.id : null,
          parentLabel: null,
          deps: [],
          ready: () => true,
          waitFor: null,
          html: `Remove the relation <b>${e(a.label)}</b> <em>${e(link.label)}</em> ${e(b.label)}`,
          why:
            link.kind === 'isa'
              ? 'the specialisation would no longer inherit from its parent'
              : link.kind === 'same'
                ? 'the two vocabularies would no longer be aligned on this concept'
                : 'action removed from the model',
          caption: draft.caption ?? `${a.label} ${link.label} ${b.label} was removed from the model.`,
          conceptId: null,
          relationId: link.id,
          relationIds: [],
          sourceId: null,
          bindingIds: [],
          attributeId: null,
          apply() {
            link.dyingAt = iso();
          },
        });
      if (link.kind === 'isa' || link.kind === 'same')
        throw new Refusal(422, 'structural_relation', 'is a and equivalent to cannot be relabelled');
      const v = (pl.action || link.label).toLowerCase();
      const reverse = !!pl.reverse;
      if (v === link.label && !reverse) throw new Refusal(422, 'no_change', 'nothing changes');
      const from = reverse ? b : a,
        to = reverse ? a : b;
      const fd = domainOfConcept(from);
      return newProposal({
        type: 'change',
        changeKind: 'edit_relation',
        title: `${from.label} ${v} ${to.label}`,
        heading: KIND_HEADING.change + (fd ? ` · ${fd.name}` : ''),
        color: NEUTRAL,
        companyId: from.companyId,
        domainId: fd ? fd.id : null,
        parentLabel: null,
        deps: [],
        ready: () => true,
        waitFor: null,
        html: `Relation <b>${e(a.label)}</b> <em>${e(link.label)}</em> ${e(b.label)} becomes <b>${e(from.label)}</b> <em>${e(v)}</em> ${e(to.label)}`,
        why: reverse ? 'direction reversed' : 'action renamed',
        caption: draft.caption ?? `The relation now reads ${from.label} ${v} ${to.label}.`,
        conceptId: null,
        relationId: link.id,
        relationIds: [],
        sourceId: null,
        bindingIds: [],
        attributeId: null,
        apply() {
          link.label = v;
          if (reverse) {
            const t = link.aId;
            link.aId = link.bId;
            link.bId = t;
          }
        },
      });
    }
    throw new Refusal(422, 'unsupported_change', `${draft.changeKind} is not available in the mock API`);
  }

  /** Like the API, a relation end given by both id and label (or neither) refuses the whole request. */
  function refuseMixedDrafts(drafts: T.ProposalDraft[]): void {
    for (const draft of drafts) {
      const end = mixedRelationEnd(draft);
      if (end) throw new Refusal(422, 'validation_failed', `exactly one of ${end}Id or ${end}Label is required`);
    }
  }

  function createFromDraft(draft: T.ProposalDraft, cascade: MProposal[]): MProposal {
    switch (draft.type) {
      case 'concept': {
        const host = conceptById(draft.parentId) || (draft.parentLabel ? findConcept(draft.parentLabel, draft.companyId) : null);
        if (!host) throw new Refusal(404, 'parent_not_found', 'the parent concept does not exist');
        if (findConcept(draft.label, host.companyId))
          throw new Refusal(409, 'duplicate_label', `${draft.label} is already in the model.`);
        return pConcept(host, draft.label, draft.domainKey, draft.action || 'relates to', draft.caption, !!draft.reverse, draft.seed);
      }
      case 'spec': {
        const host = conceptById(draft.parentId) || (draft.parentLabel ? findConcept(draft.parentLabel, draft.companyId) : null);
        if (!host) throw new Refusal(404, 'parent_not_found', 'the parent concept does not exist');
        return pSpec(host, draft.label, draft.rule || '', draft.caption, draft.domainKey, draft.seed);
      }
      case 'relation': {
        const a = conceptById(draft.aId),
          b = conceptById(draft.bId);
        if (!a || !b) throw new Refusal(404, 'concept_not_found', 'an end of the relation does not exist');
        return pRelation(a, draft.action, b, draft.caption, draft.seed);
      }
      case 'source': {
        const co = companyOf(draft.companyId);
        if (!co) throw new Refusal(404, 'company_not_found', 'company does not exist');
        return pSource(co, draft.label, draft.kindText, draft.caption, draft);
      }
      case 'bind': {
        const src = sourceById(draft.sourceId);
        if (!src) throw new Refusal(404, 'source_not_found', 'source does not exist');
        const targets = draft.conceptIds.map(conceptById).filter((c): c is MConcept => !!c);
        if (!targets.length) throw new Refusal(404, 'concept_not_found', 'no binding target exists');
        return pBind(src, targets, draft.caption, cascade);
      }
      case 'attr': {
        const n = conceptById(draft.conceptId);
        if (!n) throw new Refusal(404, 'concept_not_found', 'concept does not exist');
        return pAttr(n, [draft.name, draft.attributeType, draft.col, draft.fill, 'new'], draft.sourceId ?? null);
      }
      case 'change':
        return pChange(draft);
    }
  }

  // ------------------------------------------------------------ decisions

  /** Two specialisations of the same parent with the same name are a conflict. */
  function afterApply(): void {
    const isa = relations.filter((l) => l.kind === 'isa' && !conceptById(l.aId)?.pending && !conceptById(l.bId)?.pending);
    for (let i = 0; i < isa.length; i++)
      for (let j = i + 1; j < isa.length; j++) {
        const a = conceptById(isa[i].aId),
          b = conceptById(isa[j].aId);
        if (!a || !b) continue;
        if (
          isa[i].bId === isa[j].bId &&
          a.label === b.label &&
          !a.conflict &&
          !b.conflict &&
          !relations.some((l) => l.kind === 'clash' && ((l.aId === a.id && l.bId === b.id) || (l.aId === b.id && l.bId === a.id)))
        ) {
          setTimeout(() => {
            if (a.label !== b.label || a.dyingAt || b.dyingAt) return;
            a.conflict = b.conflict = true;
            const r = newRelation(a, b, 'clash', 130, 'conflicts with');
            emit('concept.conflict', {
              concepts: [toConcept(a), toConcept(b)],
              relation: toRelation(r),
              caption:
                'Two departments use the same name for different things. The model does not crash and does not pick one: it flags the conflict and waits for the owner.',
            });
          }, 3600);
        }
      }
  }

  function decision(p: MProposal, cascaded: MProposal[], entry: T.AuditEntry, caption?: string): T.DecisionResult {
    return { proposal: toProposal(p), artefacts: artefactsOf(p), cascaded: cascaded.map(toProposal), audit: entry, caption };
  }

  function approve(p: MProposal, bulk: boolean, cascade: MProposal[] = []): T.DecisionResult {
    if (!p.ready()) throw new Refusal(409, 'proposal_not_ready', `${p.title} waits for ${p.waitFor || 'a previous item'}`);
    if (settings.twoApprovers && p.type === 'change' && !p.second) {
      p.second = true;
      p.state = 'half_approved';
      p.why = (p.why ? p.why + ' · ' : '') + '1 of 2 approvals · a Governor must approve too';
      const entry = addAudit(p.type, `${p.title} · 1 of 2`, true, p.id);
      const result = decision(p, [], entry);
      emit('proposal.half_approved', { proposal: result.proposal, artefacts: result.artefacts, cascaded: [] }, bulk);
      return result;
    }
    p.state = 'approved';
    p.decidedAt = iso();
    const entry = addAudit(p.type, p.title, true, p.id);
    const c = conceptById(p.conceptId);
    if (c && p.type !== 'attr' && p.type !== 'change') c.pending = false;
    const r = relationById(p.relationId);
    if (r && p.type !== 'change') r.pending = false;
    const src = sourceById(p.sourceId);
    if (src && p.type === 'source') src.pending = false;
    for (const id of p.relationIds) {
      const l = relationById(id);
      if (l) l.pending = false;
    }
    if (p.apply) p.apply();
    const dom = domainById(p.domainId);
    if (dom) dom.revision += 1;
    const result = decision(p, cascade, entry, p.caption ?? undefined);
    emit('proposal.approved', { ...result, audit: undefined }, bulk);
    afterApply();
    return result;
  }

  function reject(p: MProposal, cascaded: MProposal[]): T.DecisionResult {
    p.state = 'rejected';
    p.decidedAt = iso();
    const entry = addAudit(p.type, p.title, false, p.id);
    const t = iso();
    const c = conceptById(p.conceptId);
    if (c && p.type !== 'attr' && p.type !== 'change') {
      c.dyingAt = t;
      c.pending = false;
      for (const q of open()) {
        if (q.state !== 'pending' && q.state !== 'half_approved') continue;
        if (q.conceptId && q.conceptId !== c.id && (q.type === 'concept' || q.type === 'spec')) {
          const qc = conceptById(q.conceptId);
          if (qc && descends(qc, c)) {
            reject(q, cascaded);
            cascaded.push(q);
          }
        }
      }
      for (const q of open()) {
        if (q.state !== 'pending' && q.state !== 'half_approved') continue;
        if (q.relationId) {
          const l = relationById(q.relationId);
          if (l && (l.aId === c.id || l.bId === c.id)) {
            reject(q, cascaded);
            cascaded.push(q);
          }
        }
      }
    }
    const r = relationById(p.relationId);
    if (r && p.type !== 'change') r.dyingAt = t;
    for (const id of p.relationIds) {
      const l = relationById(id);
      if (l) l.dyingAt = t;
    }
    const src = sourceById(p.sourceId);
    if (src && p.type === 'source') src.dyingAt = t;
    for (const id of p.bindingIds) bindings = bindings.filter((b) => b.id !== id);
    if (p.onReject) p.onReject();
    const result = decision(p, cascaded, entry, `${p.title} was not kept. The model only holds what its owners approved.`);
    // Rows the canvas fades out for 0.7 s leave the server at once.
    if (c && c.dyingAt) {
      relations = relations.filter((l) => l.aId !== c.id && l.bId !== c.id);
      concepts = concepts.filter((x) => x !== c);
    }
    if (src && src.dyingAt) sources = sources.filter((x) => x !== src);
    relations = relations.filter((l) => !l.dyingAt);
    emit('proposal.rejected', { ...result, audit: undefined });
    return result;
  }

  function approveAll(): T.BulkResult {
    let guard = 0,
      approved = 0,
      rounds = 0;
    while (open().some((p) => p.ready()) && guard++ < 200) {
      rounds++;
      for (const p of open().filter((p) => p.ready())) {
        approve(p, true);
        approved++;
      }
    }
    return { approved, rejected: 0, rounds, remaining: open().length, caption: 'All pending proposals are now part of the model.' };
  }

  // ------------------------------------------------------------ demo

  function reset(): void {
    companies = [];
    concepts = [];
    sources = [];
    relations = [];
    bindings = [];
    proposals = [];
    audit = [];
    sceneIdx = 0;
    coverage = false;
    appearance.theme = 'dark';
    appearance.colors = {};
    appearance.accent = '#3fb8a9';
    appearance.source = DEFAULT_BRASS;
    addCompany(HOME_COMPANY.name, HOME_COMPANY.sub);
  }

  function createCompany(body: T.CompanyCreate): T.CompanyCreated {
    if (!body?.name?.trim()) throw new Refusal(422, 'name_required', 'a company needs a name');
    const c = addCompany(body.name.trim(), (body.sub || '').trim());
    const root = conceptById(c.rootId) as MConcept;
    emit('company.created', { company: toCompany(c), root: toConcept(root) });
    const made: MProposal[] = [];
    if (body.start === 'starter_vocabulary') {
      for (const [label, dom, pred, parent] of SEED) {
        const host = findConcept(parent || c.name, c.id);
        if (!host) continue;
        const domName = c.domains.find((d) => d.key === dom)?.name;
        const p = pConcept(host, label, dom, pred, `${label} is kept in ${c.name}’s ${domName}.`, false);
        made.push(p);
        emit('proposal.created', { proposal: toProposal(p), artefacts: artefactsOf(p), cascaded: [] });
      }
    }
    addAudit('company', `${c.name} added`, true);
    return { company: toCompany(c), root: toConcept(root), proposals: made.map(toProposal) };
  }

  reset();

  // ------------------------------------------------------------ teaching

  /** A concept of the company by name, plural or singular, the reference's `resolve`. */
  function resolveLabel(np: string, companyId: string): MConcept | null {
    if (!np) return null;
    const t = title(np);
    const mine = concepts.filter((x) => x.companyId === companyId && !x.dyingAt);
    return (
      findConcept(t, companyId) ||
      mine.find((x) => x.label.toLowerCase() === np.toLowerCase()) ||
      mine.find(
        (x) => x.label.toLowerCase() === singular(np.toLowerCase()) || singular(x.label.toLowerCase()) === np.toLowerCase(),
      ) ||
      null
    );
  }

  /** The port of the reference's `teach`: intents to drafts, without writing anything. */
  function teachParse(body: { companyId: string; text: string; fromImport?: boolean }): T.TeachResult {
    const co = companyOf(body.companyId);
    if (!co) throw new Refusal(404, 'company_not_found', 'company does not exist');
    const text0 = (body.text || '').trim();
    if (!text0) throw new Refusal(422, 'text_required', 'a sentence is needed');
    const up = SCENES[sceneIdx + 1];
    if (!body.fromImport && settings.demoStory && up && up.match && up.match.test(text0))
      return { outcome: 'scene', domainKey: null, intents: [], drafts: [], statements: [], caption: '', scene: demoScenes()[sceneIdx + 1] };
    const { domainKey: domKey, text } = domainPrefix(text0);
    const key = (fallback: string | null | undefined) => (domKey || fallback || 'production') as T.DomainKey;
    const root = conceptById(co.rootId) as MConcept;
    const intents: T.Intent[] = [];
    const drafts: T.ProposalDraft[] = [];
    const made: string[] = [];
    for (const it of understand(text)) {
      if (it.kind === 'spec') {
        const parent = resolveLabel(it.obj, co.id),
          child = resolveLabel(it.subj, co.id);
        intents.push({ kind: 'spec', subject: it.subj, object: it.obj, rule: it.rule, subjectResolved: child?.id ?? null, objectResolved: parent?.id ?? null });
        if (parent && !child) {
          drafts.push({
            type: 'spec',
            companyId: co.id,
            parentId: parent.id,
            label: title(it.subj),
            rule: it.rule || '',
            domainKey: key(parent.domainKey),
            caption: `${parent.label} divides: ${title(it.subj)} inherits everything ${parent.label} is${it.rule ? ', plus the rule you gave' : ''}.`,
          });
          made.push(`${title(it.subj)} is a ${parent.label}`);
        } else if (parent && child) {
          drafts.push({ type: 'relation', aId: child.id, bId: parent.id, action: 'is a', caption: `${child.label} is a ${parent.label}: it inherits everything ${parent.label} is.` });
          made.push(`${child.label} is a ${parent.label}`);
        } else if (!parent && child) {
          drafts.push({ type: 'concept', companyId: co.id, parentId: child.id, label: title(it.obj), domainKey: key(child.domainKey), action: 'is a kind of', reverse: true });
          made.push(`${child.label} is a kind of ${title(it.obj)} (new)`);
        } else {
          drafts.push({ type: 'concept', companyId: co.id, parentId: root.id, label: title(it.obj), domainKey: key(null), action: 'has' });
          drafts.push({ type: 'spec', companyId: co.id, parentId: '', parentLabel: title(it.obj), label: title(it.subj), rule: it.rule || '', domainKey: key(null) });
          made.push(`${title(it.subj)} is a ${title(it.obj)} (both new)`);
        }
        continue;
      }
      const a = resolveLabel(it.subj, co.id),
        b = resolveLabel(it.obj, co.id);
      const pred = it.pred || 'relates to';
      intents.push({ kind: 'rel', subject: it.subj, predicate: pred, object: it.obj, subjectResolved: a?.id ?? null, objectResolved: b?.id ?? null });
      if (a && b) {
        if (a === b) continue;
        drafts.push({ type: 'relation', aId: a.id, bId: b.id, action: pred, caption: `${a.label} ${pred} ${b.label}: from ${a.label} to ${b.label}, the action on the line.` });
        made.push(`${a.label} ${pred} ${b.label}`);
      } else if (a && !b) {
        drafts.push({ type: 'concept', companyId: co.id, parentId: a.id, label: title(it.obj), domainKey: key(a.domainKey), action: pred, caption: `${title(it.obj)} is kept. ${a.label} ${pred} ${title(it.obj)}.` });
        made.push(`${a.label} ${pred} ${title(it.obj)} (new)`);
      } else if (!a && b) {
        drafts.push({ type: 'concept', companyId: co.id, parentId: b.id, label: title(it.subj), domainKey: key(b.domainKey), action: pred, reverse: true, caption: `${title(it.subj)} is kept. ${title(it.subj)} ${pred} ${b.label}.` });
        made.push(`${title(it.subj)} (new) ${pred} ${b.label}`);
      } else {
        drafts.push({ type: 'concept', companyId: co.id, parentId: root.id, label: title(it.subj), domainKey: key(null), action: 'has' });
        drafts.push({ type: 'concept', companyId: co.id, parentId: '', parentLabel: title(it.subj), label: title(it.obj), domainKey: key(null), action: pred });
        made.push(`${title(it.subj)} ${pred} ${title(it.obj)} (both new)`);
      }
    }
    if (made.length)
      return { outcome: 'understood', domainKey: (domKey as T.DomainKey) || null, intents, drafts, statements: made, caption: made.join(' · ') + '. Waiting for your approval on the right.', scene: null };
    // nothing parsed: fall back to naming the concepts mentioned
    const words = contentWords(text);
    const mine = concepts.filter((n) => n.companyId === co.id && !n.dyingAt);
    const host = mine.find((n) => words.includes(n.label.toLowerCase())) || root;
    const fresh = [...new Set(words)].filter((w) => !findConcept(title(w), co.id)).slice(0, 3);
    if (!fresh.length || !mine.some((n) => words.includes(n.label.toLowerCase())))
      return {
        outcome: 'not_understood',
        domainKey: (domKey as T.DomainKey) || null,
        intents,
        drafts: [],
        statements: [],
        caption: 'Try “<subject> <action> <object>”, “A is a B”, or “A that … is a B”. Start with “In quality, …” to choose the domain product.',
        scene: null,
      };
    return {
      outcome: 'partly_understood',
      domainKey: (domKey as T.DomainKey) || null,
      intents,
      drafts: fresh.map((w) => ({ type: 'concept' as const, companyId: co.id, parentId: host.id, label: title(w), domainKey: key(host.domainKey), action: 'relates to', caption: `${title(w)} is kept.` })),
      statements: [],
      caption: `No action found; ${fresh.map(title).join(', ')} proposed from ${host.label} with “relates to”. Click the line to give it the right action.`,
      scene: null,
    };
  }

  // ------------------------------------------------------------ routing

  const json = (status: number, body: unknown): MockResponse => ({ status, body });
  const problem = (r: Refusal): MockResponse =>
    json(r.status, { type: 'about:blank', title: r.code, status: r.status, detail: r.detail, code: r.code } satisfies T.Problem);

  function route(method: string, rawPath: string, body: unknown): MockResponse {
    const [path] = rawPath.split('?');
    const seg = path.replace(/^\/+|\/+$/g, '').split('/');
    const is = (m: string, ...parts: (string | null)[]) =>
      method === m && seg.length === parts.length && parts.every((p, i) => p === null || p === seg[i]);

    if (is('GET', 'scene')) return json(200, toScene());
    if (is('GET', 'proposals')) {
      const items = open().map(toProposal);
      return json(200, { items, page: 1, pageSize: items.length || 1, total: items.length });
    }
    if (is('POST', 'proposals')) {
      refuseMixedDrafts([body as T.ProposalDraft]);
      const cascade: MProposal[] = [];
      const p = createFromDraft(body as T.ProposalDraft, cascade);
      const out = toProposal(p);
      emit('proposal.created', { proposal: out, artefacts: out.artefacts, cascaded: [] });
      return json(202, out);
    }
    if (is('POST', 'proposals', 'batch')) {
      const drafts = (body as { drafts: T.ProposalDraft[] }).drafts || [];
      refuseMixedDrafts(drafts);
      const outs: T.Proposal[] = [];
      for (const d of drafts) {
        const p = createFromDraft(d, []);
        const out = toProposal(p);
        emit('proposal.created', { proposal: out, artefacts: out.artefacts, cascaded: [] });
        outs.push(out);
      }
      return json(202, outs);
    }
    if (is('POST', 'proposals', 'approve-all')) return json(200, approveAll());
    if (is('POST', 'proposals', 'reject-all')) {
      let rejected = 0;
      for (const p of open()) {
        if (p.state !== 'pending' && p.state !== 'half_approved') continue;
        reject(p, []);
        rejected++;
      }
      return json(200, { approved: 0, rejected, rounds: 1, remaining: open().length, caption: 'All pending proposals were discarded.' } satisfies T.BulkResult);
    }
    if (is('POST', 'proposals', 'finalise-all')) {
      const bulk = approveAll();
      const cells = concepts.filter((n) => n.kind === 'concept' && !n.dyingAt).length,
        bound = concepts.filter((n) => n.bound).length,
        same = relations.filter((l) => l.kind === 'same').length;
      addAudit('demo', 'finalised all scenes', true);
      return json(200, {
        companies: companies.length,
        concepts: cells,
        bound,
        equivalences: same,
        approved: bulk.approved,
        scenesPlayed: 0,
        caption: `${companies.length} compan${companies.length === 1 ? 'y' : 'ies'}, ${cells} concepts, ${bound} bound to data, ${same} equivalences. Everything approved.`,
      } satisfies T.FinaliseResult);
    }
    if (is('GET', 'proposals', null)) {
      const p = proposals.find((x) => x.id === seg[1]);
      if (!p) throw new Refusal(404, 'proposal_not_found', 'proposal does not exist');
      return json(200, toProposal(p));
    }
    if (is('POST', 'proposals', null, 'approve') || is('POST', 'proposals', null, 'second-approve')) {
      const p = proposals.find((x) => x.id === seg[1]);
      if (!p) throw new Refusal(404, 'proposal_not_found', 'proposal does not exist');
      if (p.state !== 'pending' && p.state !== 'half_approved') throw new Refusal(409, 'proposal_decided', 'already decided');
      if (seg[2] === 'second-approve' && p.state !== 'half_approved')
        throw new Refusal(409, 'proposal_not_half_approved', 'the proposal is not half approved');
      return json(200, approve(p, false));
    }
    if (is('POST', 'proposals', null, 'reject')) {
      const p = proposals.find((x) => x.id === seg[1]);
      if (!p) throw new Refusal(404, 'proposal_not_found', 'proposal does not exist');
      if (p.state !== 'pending' && p.state !== 'half_approved') throw new Refusal(409, 'proposal_decided', 'already decided');
      return json(200, reject(p, []));
    }
    if (is('POST', 'companies')) return json(201, createCompany(body as T.CompanyCreate));
    if (is('GET', 'companies')) {
      const items = companies.map(toCompany);
      return json(200, { items, page: 1, pageSize: items.length || 1, total: items.length });
    }
    if (is('PATCH', 'domain-products', null)) {
      const d = domainById(seg[1]);
      if (!d) throw new Refusal(404, 'domain_not_found', 'domain product does not exist');
      const patch = body as { hidden?: boolean };
      if (typeof patch.hidden === 'boolean') d.hidden = patch.hidden;
      emit('domain_product.changed', { domainProduct: toDomain(d) });
      return json(200, toDomain(d));
    }
    if (is('GET', 'settings')) return json(200, { ...settings });
    if (is('PATCH', 'settings')) {
      const patch = body as T.SettingsPatch;
      for (const k of Object.keys(patch) as (keyof T.SettingsPatch)[]) {
        if (k === 'refresh') settings.refresh = patch.refresh as T.RefreshInterval;
        else if (typeof patch[k] === 'boolean') (settings as unknown as Record<string, boolean>)[k] = patch[k] as boolean;
        addAudit('setting', `${k} ${patch[k] === true ? 'enabled' : patch[k] === false ? 'disabled' : String(patch[k])}`, true);
      }
      emit('settings.changed', { settings: { ...settings } });
      return json(200, { ...settings });
    }
    if (is('GET', 'appearance')) return json(200, toAppearance());
    if (is('PATCH', 'appearance')) {
      const patch = body as T.AppearancePatch;
      if (patch.theme) {
        appearance.theme = patch.theme;
        addAudit('setting', `${patch.theme} mode`, true);
      }
      if (patch.colors) Object.assign(appearance.colors, patch.colors);
      if (patch.accent) appearance.accent = patch.accent;
      if (patch.source) appearance.source = patch.source;
      emit('appearance.changed', { appearance: toAppearance() });
      return json(200, toAppearance());
    }
    if (is('PUT', 'view-state')) {
      const vs = body as Partial<T.ViewState>;
      if (typeof vs.coverage === 'boolean') coverage = vs.coverage;
      if (typeof vs.sceneIdx === 'number') sceneIdx = vs.sceneIdx;
      return json(200, { coverage, sceneIdx } satisfies T.ViewState);
    }
    if (is('POST', 'teach', 'parse')) return json(200, teachParse(body as { companyId: string; text: string; fromImport?: boolean }));
    if (is('GET', 'demo', 'scenes')) return json(200, { sceneIdx, scenes: demoScenes() } satisfies T.DemoScenes);
    if (is('POST', 'demo', 'next')) {
      const scenes = demoScenes();
      if (sceneIdx >= scenes.length - 1) throw new Refusal(409, 'end_of_story', 'the story has ended');
      sceneIdx += 1;
      const scene = scenes[sceneIdx];
      emit('demo.scene_played', { sceneIdx, scene });
      return json(200, { sceneIdx, scene, proposals: [] } satisfies T.DemoNext);
    }
    if (is('POST', 'demo', 'reset')) {
      reset();
      return json(200, toScene());
    }
    if (is('GET', 'healthz')) return json(200, { status: 'ok' });
    throw new Refusal(404, 'not_found', `${method} ${path} is not part of the mock API`);
  }

  return {
    handle(method, path, body) {
      try {
        return route(method.toUpperCase(), path, body);
      } catch (e) {
        if (e instanceof Refusal) return problem(e);
        throw e;
      }
    },
  };
}
