/**
 * In-browser mock of the Ontaix API over an in-memory store seeded from the reference
 * constants. It answers the routes the Studio canvas uses with the shapes of
 * contracts/openapi.yaml and publishes every change on the live event bus, the way the real
 * API does over the WebSocket. Proposal text, readiness and side effects are the server-side
 * port of the reference's `pConcept`, `pSpec`, `pRelation`, `pSource`, `pBind`, `pAttr`,
 * `approve`, `reject` and `afterApply` (reference lines 573-607). Tenant domains, pending-draft
 * edits with revisions, deletion impact, bulk deletion and the company-creation setting follow
 * contracts/openapi.yaml.
 */
import { DEFAULT_BRASS, DOMAIN_R, DOMAIN_TEMPLATES, C, MAX_DOMAINS, NEUTRAL } from '../../canvas/constants';
import { contentWords, domainPrefix, singular, title, understand } from '../../nl/parser';
import { nowDate } from '../../runtime/clock';
import { random } from '../../runtime/rng';
import { escapeHtml } from '../../shell/sanitize';
import { mixedRelationEnd } from '../drafts';
import { liveEvents, type EventBus, type EventType } from '../events';
import type * as T from '../types';
import { createDirectory, DirectoryRefusal, pageOf, parseListArgs } from './directory';
import { detectImport as detectFile } from './detect';
import { extractDocument, ExtractRefusal } from './extract';
import { mapOntologyFile } from './ontology';
import { ATTR, CATALOG, DISCOVER, generic, HOME_COMPANY, RECORDS, SEED, type AttrSpec } from './seed';

interface MCompany {
  id: string;
  key: string;
  name: string;
  sub: string;
  position: number;
  rootId: string;
  domains: MDomain[];
}

/** A company's domain product; its name, owner and colour are the tenant domain's. */
interface MDomain {
  id: string;
  companyId: string;
  key: T.DomainKey;
  revision: number;
  hidden: boolean;
}

/** A tenant domain: a template or a custom domain, the same in every company. */
interface MTenantDomain {
  key: T.DomainKey;
  name: string;
  owner: string;
  defaultColor: string;
  template: boolean;
  position: number;
  revision: number;
}

interface MAttr {
  id: string;
  conceptId: string;
  sourceId: string | null;
  name: string;
  type: T.AttributeType;
  col: string | null;
  fill: number | null;
  value: string | null;
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
  /** Further concepts a decision changed, reported with its artefacts. */
  conceptIds?: string[];
  /** Further domain products a decision changed, reported with its artefacts. */
  domainIds?: string[];
  /** Incremented by every in-place edit of the pending draft. */
  revision: number;
  createdAt: string;
  decidedAt: string | null;
  second: boolean;
  origin: T.Origin;
  originDetail: T.OriginDetail | null;
  apply?: () => void;
  onReject?: () => void;
}

export interface MockResponse {
  status: number;
  body: unknown;
  /** The lines of a newline-delimited JSON answer, sent in place of `body`. */
  lines?: unknown[];
}

/** A stored ontology import: the mapped tree, kept for 24 hours for its actor. */
interface MOntologyImport {
  result: T.OntologyImportResult;
  fileName: string;
  expiresAt: number;
  submitted: boolean;
}

/** A stored document import: its sentences, their positions and the per-sentence reuse counters. */
interface MImport {
  id: string;
  fileName: string;
  mediaType: T.ImportMediaType;
  sentences: string[];
  positions: (T.DocumentPosition | null)[];
  parseCounts: number[];
  drafted: boolean[];
  expiresAt: number;
}

export interface MockServer {
  handle(method: string, path: string, body?: unknown): MockResponse;
  /** `POST /import/sentences`: reads and extracts the uploaded file, then stores the import. */
  importDocument(file: { name: string; type: string; bytes: Uint8Array }, fields?: Record<string, string>): Promise<MockResponse>;
  /** `POST /import/detect`: whether the uploaded file is a document or an ontology. */
  detectImport(file: { name: string; type: string; bytes: Uint8Array }): Promise<MockResponse>;
  /** `POST /ontology-imports`: maps the uploaded file into a stored draft tree. */
  importOntology(file: { name: string; type: string; bytes: Uint8Array }, fields: Record<string, string>): Promise<MockResponse>;
}

/** Birth draws of a concept: angle noise, node seed and link bend. */
export interface MockBirth {
  noise: number;
  node: number;
  link: number;
}

export interface MockHooks {
  /**
   * Receives the birth draws of a concept the server proposes on its own (a new company's
   * starter vocabulary). With it, the server draws noise, node seed and link bend in the
   * reference's order and the canvas divides with them; without it, the server draws the bend
   * only and the canvas draws the rest.
   */
  rememberBirth?(companyId: string, label: string, draws: MockBirth): void;
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
const HEX = /^#[0-9a-f]{6}$/i;
const DOMAIN_KEY = /^[a-z][a-z0-9_]{1,39}$/;
/** The API's label rules: 1 to 120 characters, no markup, control or format characters, no surrounding space. */
const LABEL_MAX = 120;
const ACTION_MAX = 60;
const NAME_MAX = 60;
const BULK_CONCEPTS = 200;
const BULK_PRODUCTS = 20;
/** Names the deletion impact lists before the rest collapse into a count. */
const IMPACT_NAMES = 6;
const forbiddenText = (s: string) => /[<>\u0000-\u001f\u007f\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff]/.test(s) || s !== s.trim();
/** An import serves parses and drafts for one hour. */
const IMPORT_LIFETIME_MS = 60 * 60 * 1000;
/** An ontology import serves its submission for 24 hours. */
const ONTOLOGY_IMPORT_LIFETIME_MS = 24 * 60 * 60 * 1000;
const ONTOLOGY_FORMATS: T.OntologyFormat[] = ['rdf_xml', 'turtle', 'owl_xml', 'json_ld', 'n_triples', 'obo', 'csv', 'xlsx'];
/** A cited sentence may be parsed this many times. */
const IMPORT_PARSES_PER_SENTENCE = 3;
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

export function createMockServer(bus: EventBus = liveEvents, hooks: MockHooks = {}): MockServer {
  let counter = 0;
  const uuid = () => `00000000-0000-4000-8000-${String(++counter).padStart(12, '0')}`;
  const iso = () => nowDate().toISOString();
  /** Label text as it may appear inside proposal html: escaped, so markup only ever comes from the builders. */
  const e = escapeHtml;

  let companies: MCompany[] = [];
  let domains: MTenantDomain[] = [];
  let concepts: MConcept[] = [];
  let sources: MSource[] = [];
  let relations: MRelation[] = [];
  let bindings: MBinding[] = [];
  let proposals: MProposal[] = [];
  let audit: T.AuditEntry[] = [];
  let imports: MImport[] = [];
  const ontologyImports = new Map<string, MOntologyImport>();
  let expansions: MExpansion[] = [];
  let extractions: MExtraction[] = [];
  let sequence = 0;
  let coverage = false;
  /** Provenance given to the proposals the current request creates. */
  let provenance: { origin: T.Origin; originDetail: T.OriginDetail | null; why?: string } = { origin: 'text', originDetail: null };
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
    companyCreation: true,
    crossCompany: true,
    animations: true,
    coverageDefault: false,
    legend: true,
    readOnlyConnectors: true,
    refresh: '15 min',
    agentAccess: true,
    costCap: true,
    llmMonthlyTokenCap: 2_000_000,
    ocrMonthlyPageCap: 1000,
  };
  const appearance = { theme: 'dark' as 'dark' | 'light', colors: {} as Record<string, string>, accent: '#3fb8a9', source: DEFAULT_BRASS };
  const directory = createDirectory({
    companies: () => companies.map((c) => ({ id: c.id, name: c.name })),
    addAudit: (kind, what, ok) => {
      addAudit(kind, what, ok);
    },
    agentAccess: () => settings.agentAccess,
  });

  const tenantDomain = (key: string | null | undefined) => domains.find((d) => d.key === key) || null;
  const domainColour = (key: string) => appearance.colors[key] || tenantDomain(key)?.defaultColor || NEUTRAL;
  const colourOf = (d: MDomain) => domainColour(d.key);
  const nameOf = (d: MDomain) => tenantDomain(d.key)?.name ?? d.key;
  const ownerOf = (d: MDomain) => tenantDomain(d.key)?.owner ?? '';
  const companyOf = (id: string) => companies.find((c) => c.id === id) || null;
  const conceptById = (id: string | null | undefined) => concepts.find((c) => c.id === id) || null;
  const sourceById = (id: string | null | undefined) => sources.find((c) => c.id === id) || null;
  const relationById = (id: string | null | undefined) => relations.find((c) => c.id === id) || null;
  const domainById = (id: string | null) => companies.flatMap((c) => c.domains).find((d) => d.id === id) || null;
  const domainOfConcept = (c: MConcept) =>
    c.domainKey ? companyOf(c.companyId)?.domains.find((d) => d.key === c.domainKey) || null : null;
  const domainByKey = (companyId: string, key: string | null | undefined) =>
    companyOf(companyId)?.domains.find((d) => d.key === key) || null;
  /** The company's product for a tenant domain, created when its first concept joins; null for a key the tenant lacks. */
  function ensureProduct(companyId: string, key: string | null | undefined): MDomain | null {
    const have = domainByKey(companyId, key);
    if (have) return have;
    const co = companyOf(companyId);
    const td = tenantDomain(key);
    if (!co || !td) return null;
    const d: MDomain = { id: uuid(), companyId, key: td.key, revision: 0, hidden: false };
    co.domains.push(d);
    co.domains.sort((a, b) => (tenantDomain(a.key)?.position ?? 0) - (tenantDomain(b.key)?.position ?? 0));
    return d;
  }
  /** The product a draft's `domainKey` names: the host's when absent, `422` when the tenant has no such domain. */
  function productForDraft(companyId: string, key: string | null | undefined, host: MConcept): MDomain | null {
    if (!key) return domainOfConcept(host);
    const d = ensureProduct(companyId, key);
    if (!d) throw new Refusal(422, 'validation_failed', `${key} is not a domain of the tenant`);
    return d;
  }
  /** A living concept by label inside a company, the reference's `find`. */
  const findConcept = (label: string, companyId: string) =>
    concepts.find((n) => n.label.toLowerCase() === label.toLowerCase() && n.companyId === companyId && !n.dyingAt) ||
    null;
  const open = () => proposals.filter((p) => p.state === 'pending' || p.state === 'half_approved');

  /** A decision entry: the proposal's company and the template key of its domain product. */
  function addProposalAudit(p: MProposal, what: string, ok: boolean): T.AuditEntry {
    return addAudit(p.type, what, ok, p.id, p.companyId ? [p.companyId] : [], domainById(p.domainId)?.key ?? null, p.origin);
  }

  function addAudit(
    kind: string,
    what: string,
    ok: boolean,
    proposalId: string | null = null,
    companyIds: string[] = [],
    domainKey: T.DomainKey | null = null,
    origin: T.Origin | null = null,
  ): T.AuditEntry {
    const e: T.AuditEntry = { id: audit.length + 1, at: iso(), actor: ACTOR, kind, what, ok, proposalId, origin, companyIds, domainKey };
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
      scope: ad === bd ? (ad ? nameOf(ad) : 'company') : `${ad ? nameOf(ad) : 'company'} → ${bd ? nameOf(bd) : 'company'}`,
      state: l.pending ? 'awaiting approval' : 'approved',
    };
  };

  const toDomain = (d: MDomain): T.DomainProduct => {
    const members = concepts.filter((n) => n.domainKey === d.key && n.companyId === d.companyId && !n.dyingAt);
    return {
      id: d.id,
      companyId: d.companyId,
      key: d.key,
      name: nameOf(d),
      owner: ownerOf(d),
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
    const cs = [p.conceptId, ...(p.conceptIds || [])].map(conceptById).filter((x): x is MConcept => !!x);
    const rs = [p.relationId, ...p.relationIds].map(relationById).filter((x): x is MRelation => !!x);
    const ss = [p.sourceId].map(sourceById).filter((x): x is MSource => !!x);
    const bs = p.bindingIds.map((id) => bindings.find((b) => b.id === id)).filter((x): x is MBinding => !!x);
    const as = p.attributeId ? concepts.flatMap((c) => c.attributes).filter((a) => a.id === p.attributeId) : [];
    const ds = [p.domainId, ...(p.domainIds || [])].map(domainById).filter((x): x is MDomain => !!x);
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
    origin: p.origin,
    originDetail: p.originDetail,
    approvals: [],
    revision: p.revision,
    createdAt: p.createdAt,
    decidedAt: p.decidedAt,
    artefacts: artefactsOf(p),
    openBelow: branchOf(p).length,
  });

  const toAppearance = (): T.Appearance => ({
    theme: appearance.theme,
    colors: Object.fromEntries(domains.map((d) => [d.key, appearance.colors[d.key] || d.defaultColor])),
    accent: appearance.accent,
    source: appearance.source,
    defaults: { colors: Object.fromEntries(domains.map((d) => [d.key, d.defaultColor])), accent: '#3fb8a9', source: DEFAULT_BRASS },
  });

  const toTenantDomain = (d: MTenantDomain): T.TenantDomain => ({
    key: d.key,
    name: d.name,
    owner: d.owner,
    color: appearance.colors[d.key] || d.defaultColor,
    defaultColor: d.defaultColor,
    template: d.template,
    position: d.position,
    revision: d.revision,
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
    viewState: { coverage },
    connectors: CATALOG.map(([code, name, category, scopeText]) => ({ code, name, category, scopeText })),
  });

  // ------------------------------------------------------------ model helpers

  /** A relation row; the bend is the client's draw when the draft carried one, else drawn here. */
  function newRelation(a: MConcept, b: MConcept, kind: T.RelationKind, rest: number, label: string, seed?: number): MRelation {
    const bend = typeof seed === 'number' && seed >= 0 && seed <= 1 ? seed : random();
    const l: MRelation = { id: uuid(), aId: a.id, bId: b.id, kind, label, rest, seed: bend, pending: false, dyingAt: null };
    relations.push(l);
    return l;
  }

  function newProposal(
    p: Omit<MProposal, 'id' | 'state' | 'revision' | 'createdAt' | 'decidedAt' | 'second' | 'origin' | 'originDetail'>,
  ): MProposal {
    const full: MProposal = { ...p, id: uuid(), state: 'pending', revision: 0, createdAt: iso(), decidedAt: null, second: false, ...provenance };
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
      domains: domains.filter((t) => t.template).map((t) => ({ id: uuid(), companyId: id, key: t.key, revision: 0, hidden: false })),
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
    checkLabel(label);
    checkAction(pred);
    const dom = productForDraft(host.companyId, domainKey, host);
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
      heading: KIND_HEADING.concept + (dom ? ` · ${nameOf(dom)}` : ''),
      color: dom ? colourOf(dom) : NEUTRAL,
      companyId: host.companyId,
      domainId: dom ? dom.id : null,
      parentLabel,
      deps: [parentLabel],
      ready: () => !host.pending && !host.dyingAt && concepts.includes(host),
      waitFor: parentLabel,
      html: conceptHtml(label, parentLabel, pred, reverse),
      why: dom ? `domain product: ${nameOf(dom)}` : '',
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
    checkLabel(label);
    const dom = productForDraft(host.companyId, domainKey, host);
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
      heading: KIND_HEADING.spec + (dom ? ` · ${nameOf(dom)}` : ''),
      color: dom ? colourOf(dom) : hostDom ? colourOf(hostDom) : C.root,
      companyId: host.companyId,
      domainId: dom ? dom.id : null,
      parentLabel,
      deps: [parentLabel],
      ready: () => !host.pending && !host.dyingAt && concepts.includes(host),
      waitFor: parentLabel,
      html: specHtml(label, parentLabel),
      why: (rule ? `rule: ${rule}` : '') + (dom ? ` · domain product: ${nameOf(dom)}` : ''),
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
      html: relationHtml(a, pred, b),
      why: xco
        ? `across companies: ${aCo?.name} ↔ ${bCo?.name}`
        : cross
          ? `across domain products: ${ad ? nameOf(ad) : 'company'} → ${bd ? nameOf(bd) : 'company'}`
          : `inside ${ad ? nameOf(ad) : 'the company'}`,
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
    const attr: MAttr = { id: uuid(), conceptId: n.id, sourceId, name: a[0], type: a[1] as T.AttributeType, col: a[2], fill: a[3], value: null, state: 'proposed' };
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

  /** A taught attribute: a stated value, no column or fill; it waits for a pending concept. */
  function pTaught(n: MConcept, name: string, type: T.AttributeType, value: string): MProposal {
    const key = name.toLowerCase();
    if (n.attributes.some((x) => x.name.toLowerCase() === key)) throw new Refusal(409, 'duplicate_attribute', `${n.label} already has ${key}`);
    const attr: MAttr = { id: uuid(), conceptId: n.id, sourceId: null, name: key, type, col: null, fill: null, value, state: 'proposed' };
    n.attributes.push(attr);
    return newProposal({
      type: 'attr',
      changeKind: null,
      title: `${n.label}.${key}`,
      heading: KIND_HEADING.attr,
      color: toConcept(n).color ?? NEUTRAL,
      companyId: n.companyId,
      domainId: null,
      parentLabel: null,
      deps: n.pending ? [n.label] : [],
      ready: () => !n.pending,
      waitFor: n.pending ? n.label : null,
      html: `<b>${e(n.label)}</b> has <b>${e(key)}</b> <i>· ${e(type)} · ${e(value)}</i>`,
      why: 'taught · not yet in the model',
      caption: `${n.label} ${key}: ${value} is now part of the model.`,
      conceptId: null,
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
            .map((a) => ({ id: uuid(), conceptId: n.id, sourceId: src.id, name: a[0], type: a[1] as T.AttributeType, col: a[2], fill: a[3], value: null, state: 'approved' as const }));
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
          const r = newRelation(p, q, 'isa', 300, 'is a');
          this.conceptIds = [q.id, p.id];
          this.relationIds = [r.id];
        },
      });
    }
    if (draft.changeKind === 'rename') {
      const n = conceptById(pl.conceptId);
      const name = pl.newLabel || '';
      if (!n) throw new Refusal(404, 'concept_not_found', 'concept does not exist');
      if (!name || name === n.label) throw new Refusal(422, 'same_label', 'the new label equals the current one');
      checkLabel(name);
      if (findConcept(name, n.companyId)) throw new Refusal(409, 'duplicate_label', `${name} is already in the model.`);
      const d = domainOfConcept(n);
      return newProposal({
        type: 'change',
        changeKind: 'rename',
        title: `Rename ${n.label} to ${name}`,
        heading: KIND_HEADING.change + (d ? ` · ${nameOf(d)}` : ''),
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
        heading: KIND_HEADING.change + (d ? ` · ${nameOf(d)}` : ''),
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
          heading: KIND_HEADING.change + (ad ? ` · ${nameOf(ad)}` : ''),
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
      checkAction(v);
      const from = reverse ? b : a,
        to = reverse ? a : b;
      const fd = domainOfConcept(from);
      return newProposal({
        type: 'change',
        changeKind: 'edit_relation',
        title: `${from.label} ${v} ${to.label}`,
        heading: KIND_HEADING.change + (fd ? ` · ${nameOf(fd)}` : ''),
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
    if (draft.changeKind === 'unbind') {
      const b = bindings.find((x) => x.id === pl.bindingId && !x.pending);
      if (!b) throw new Refusal(404, 'binding_not_found', 'binding does not exist');
      const n = conceptById(b.conceptId) as MConcept,
        src = sourceById(b.sourceId) as MSource;
      const d = domainOfConcept(n);
      return newProposal({
        type: 'change',
        changeKind: 'unbind',
        title: `Unbind ${n.label} from ${src.label}`,
        heading: KIND_HEADING.change + (d ? ` · ${nameOf(d)}` : ''),
        color: appearance.source,
        companyId: n.companyId,
        domainId: d ? d.id : null,
        parentLabel: null,
        deps: [],
        ready: () => true,
        waitFor: null,
        html: `Unbind <b>${e(n.label)}</b> from <b>${e(src.label)}</b>`,
        why: 'attributes stay as declared',
        caption: draft.caption ?? `${n.label} is no longer fed by ${src.label}.`,
        conceptId: n.id,
        relationId: null,
        relationIds: [],
        sourceId: null,
        bindingIds: [],
        attributeId: null,
        apply() {
          bindings = bindings.filter((x) => x !== b);
          if (n.bound === b) n.bound = null;
        },
      });
    }
    if (draft.changeKind === 'remove_source' || draft.changeKind === 'rename_source') {
      const src = sourceById(pl.sourceId);
      if (!src || src.dyingAt) throw new Refusal(404, 'source_not_found', 'source does not exist');
      if (draft.changeKind === 'rename_source') {
        const name = (pl.newLabel || '').trim();
        if (!name || name === src.label) throw new Refusal(422, 'same_label', 'the new label equals the current one');
        return newProposal({
          type: 'change',
          changeKind: 'rename_source',
          title: `Rename ${src.label} to ${name}`,
          heading: KIND_HEADING.change,
          color: appearance.source,
          companyId: src.companyId,
          domainId: null,
          parentLabel: null,
          deps: [],
          ready: () => true,
          waitFor: null,
          html: `Rename <b>${e(src.label)}</b> to <b>${e(name)}</b>`,
          why: 'bindings keep pointing at it',
          caption: draft.caption ?? `${src.label} is now called ${name}.`,
          conceptId: null,
          relationId: null,
          relationIds: [],
          sourceId: src.id,
          bindingIds: [],
          attributeId: null,
          apply() {
            src.label = name;
          },
        });
      }
      const fed = bindings.filter((b) => b.sourceId === src.id).length;
      return newProposal({
        type: 'change',
        changeKind: 'remove_source',
        title: `Remove ${src.label}`,
        heading: KIND_HEADING.change,
        color: C.conflict,
        companyId: src.companyId,
        domainId: null,
        parentLabel: null,
        deps: [],
        ready: () => true,
        waitFor: null,
        html: `Disconnect data source <b>${e(src.label)}</b> and unbind ${fed} concept${fed === 1 ? '' : 's'}`,
        why: 'the concepts keep their attributes as declared; counts and freshness disappear',
        caption: draft.caption ?? `${src.label} was disconnected.`,
        conceptId: null,
        relationId: null,
        relationIds: [],
        sourceId: src.id,
        bindingIds: [],
        attributeId: null,
        apply() {
          for (const b of bindings.filter((x) => x.sourceId === src.id)) {
            const n = conceptById(b.conceptId);
            if (n && n.bound === b) n.bound = null;
          }
          bindings = bindings.filter((x) => x.sourceId !== src.id);
          src.dyingAt = iso();
        },
      });
    }
    if (draft.changeKind === 'remove_company') {
      const co = companyOf(pl.companyId || '');
      if (!co) throw new Refusal(404, 'company_not_found', 'company does not exist');
      if (co.position === 0 || companies.length < 2) throw new Refusal(409, 'home_company', 'the home company cannot be removed');
      const impact = deletionImpact({ companyId: co.id, wholeCompany: true });
      return newProposal({
        type: 'change',
        changeKind: 'remove_company',
        title: `Remove ${co.name}`,
        heading: KIND_HEADING.change,
        color: C.conflict,
        companyId: co.id,
        domainId: null,
        parentLabel: null,
        deps: [],
        ready: () => true,
        waitFor: null,
        html: `Remove <b>${e(co.name)}</b> from the portfolio with its ${impactHtml(impact, true)}`,
        why: 'every open proposal touching the company is rejected · equivalences to other companies are removed too',
        caption: draft.caption ?? `${co.name} left the view.`,
        conceptId: null,
        relationId: null,
        relationIds: [],
        sourceId: null,
        bindingIds: [],
        attributeId: null,
        apply() {
          const ids = new Set(concepts.filter((x) => x.companyId === co.id).map((x) => x.id));
          for (const q of open()) if (q !== this && touchesCompany(q, co.id, ids)) reject(q, []);
          relations = relations.filter((l) => !ids.has(l.aId) && !ids.has(l.bId));
          bindings = bindings.filter((b) => !ids.has(b.conceptId));
          concepts = concepts.filter((x) => !ids.has(x.id));
          sources = sources.filter((x) => x.companyId !== co.id);
          companies = companies.filter((x) => x !== co);
        },
      });
    }
    if (draft.changeKind === 'create_domain') return pCreateDomain({ name: pl.name || '', color: pl.color || '', owner: pl.owner });
    if (draft.changeKind === 'edit_domain') return pEditDomain(pl.domainKey || '', { name: pl.name, color: pl.color, owner: pl.owner });
    if (draft.changeKind === 'delete_domain') return pDeleteDomain(pl.domainProductId || '');
    if (draft.changeKind === 'move_concept_domain') return pMoveConcept(pl.conceptId || '', pl.domainKey || '');
    if (draft.changeKind === 'delete_bulk')
      return pBulkDelete({ companyId: pl.companyId || '', conceptIds: pl.conceptIds, domainProductIds: pl.domainProductIds });
    throw new Refusal(422, 'unsupported_change', `${draft.changeKind} is not available in the mock API`);
  }

  // ------------------------------------------------------------ label rules, proposal text

  function checkLabel(label: string): void {
    if (typeof label !== 'string' || !label.length || label.length > LABEL_MAX || forbiddenText(label))
      throw new Refusal(422, 'validation_failed', `a label holds 1 to ${LABEL_MAX} characters without markup, control characters or surrounding space`);
  }

  function checkAction(action: string): void {
    if (typeof action !== 'string' || !action.length || action.length > ACTION_MAX || forbiddenText(action))
      throw new Refusal(422, 'validation_failed', `an action holds 1 to ${ACTION_MAX} characters without markup, control characters or surrounding space`);
  }

  function checkName(name: string): void {
    if (typeof name !== 'string' || !name.length || name.length > NAME_MAX || forbiddenText(name))
      throw new Refusal(422, 'validation_failed', `a name holds 1 to ${NAME_MAX} characters without markup, control characters or surrounding space`);
  }

  const conceptHtml = (label: string, parentLabel: string, pred: string, reverse: boolean) =>
    reverse
      ? `<b>${e(label)}</b> <em>· ${e(label)} <b>${e(pred)}</b> ${e(parentLabel)}</em>`
      : `<b>${e(label)}</b> <em>· ${e(parentLabel)} <b>${e(pred)}</b> ${e(label)}</em>`;

  const specHtml = (label: string, parentLabel: string) => `<b>${e(label)}</b> <em>is a ${e(parentLabel)}</em>`;

  function relationHtml(a: MConcept, pred: string, b: MConcept): string {
    const xco = a.companyId !== b.companyId;
    const aCo = companyOf(a.companyId),
      bCo = companyOf(b.companyId);
    return `${e(a.label)}${xco ? ' <em>(' + e(aCo?.name ?? '') + ')</em>' : ''} <b>${e(pred)}</b> ${e(b.label)}${xco ? ' <em>(' + e(bCo?.name ?? '') + ')</em>' : ''}`;
  }

  // ------------------------------------------------------------ editing a pending draft

  /**
   * `PATCH /proposals/{id}`: a pending concept, spec or relation draft changes label and/or action
   * in place. Every creation check re-runs, the text is rebuilt, dependants naming the old label
   * are rewritten, the revision increments and `proposal.changed` is emitted.
   */
  function editProposal(p: MProposal, body: T.ProposalEdit): T.Proposal {
    if (!body || typeof body !== 'object' || !Number.isInteger(body.revision) || body.revision < 0)
      throw new Refusal(422, 'validation_failed', 'revision is required');
    if (body.label === undefined && body.action === undefined) throw new Refusal(422, 'validation_failed', 'label or action is required');
    if (p.state !== 'pending' || (p.type !== 'concept' && p.type !== 'spec' && p.type !== 'relation'))
      throw new Refusal(409, 'proposal_not_editable', `${p.title} cannot be edited`);
    if (body.revision !== p.revision) throw new Refusal(409, 'proposal_changed', `${p.title} was edited since you read it`);
    if (p.type === 'spec' && body.action !== undefined) throw new Refusal(422, 'validation_failed', 'a specialisation has no action');
    if (p.type === 'relation' && body.label !== undefined) throw new Refusal(422, 'validation_failed', 'a relation has no label');
    const rel = relationById(p.relationId);
    if (!rel) throw new Refusal(409, 'proposal_not_editable', `${p.title} cannot be edited`);
    if (p.type === 'relation') {
      const action = (body.action as string).toLowerCase();
      checkAction(action);
      if (action === 'is a' || action === 'equivalent to') throw new Refusal(422, 'validation_failed', 'is a and equivalent to are not relation actions');
      const a = conceptById(rel.aId),
        b = conceptById(rel.bId);
      if (!a || !b) throw new Refusal(409, 'proposal_not_editable', `${p.title} cannot be edited`);
      if (relations.some((l) => l !== rel && l.aId === a.id && l.bId === b.id && l.label === action && !l.dyingAt))
        throw new Refusal(409, 'duplicate_relation', `${a.label} ${action} ${b.label} is already in the model.`);
      const before = p.title;
      rel.label = action;
      p.title = `${a.label} ${action} ${b.label}`;
      p.html = relationHtml(a, action, b);
      finishEdit(p, before);
      emit('relation.changed', { relation: toRelation(rel) });
      return toProposal(p);
    }
    const c = conceptById(p.conceptId);
    if (!c || !p.parentLabel) throw new Refusal(409, 'proposal_not_editable', `${p.title} cannot be edited`);
    const label = body.label === undefined ? c.label : title(body.label);
    if (body.label !== undefined) {
      checkLabel(label);
      const taken = findConcept(label, c.companyId);
      if (taken && taken !== c) throw new Refusal(409, 'duplicate_label', `${label} is already in the model.`);
    }
    const reverse = rel.aId === c.id;
    const action = body.action === undefined ? rel.label : (body.action as string).toLowerCase();
    if (body.action !== undefined) checkAction(action);
    const old = c.label;
    const before = p.title;
    c.label = label;
    rel.label = action;
    p.title = label;
    p.html = p.type === 'spec' ? specHtml(label, p.parentLabel) : conceptHtml(label, p.parentLabel, action, reverse);
    if (old !== label)
      for (const q of open()) {
        if (q === p || q.companyId !== p.companyId) continue;
        if (!q.deps.includes(old) && q.parentLabel !== old) continue;
        q.deps = q.deps.map((x) => (x === old ? label : x));
        if (q.parentLabel === old) q.parentLabel = label;
        if (q.waitFor === old) q.waitFor = label;
        else if (q.waitFor && q.type === 'relation') q.waitFor = q.deps.join(' and ');
        q.html = q.html.split(e(old)).join(e(label));
        if (q.title.includes(old)) q.title = q.title.split(old).join(label);
      }
    finishEdit(p, before);
    emit('concept.changed', { concept: toConcept(c) });
    return toProposal(p);
  }

  function finishEdit(p: MProposal, before: string): void {
    p.revision += 1;
    addAudit('edit', `${before} → ${p.title}`, true, p.id, p.companyId ? [p.companyId] : [], domainById(p.domainId)?.key ?? null, p.origin);
    const out = toProposal(p);
    emit('proposal.changed', { proposal: out, artefacts: out.artefacts, cascaded: [] });
  }

  // ------------------------------------------------------------ deletion impact

  /** The approved, live concepts born from any of `roots`, transitively, the roots excluded; pending ones are cascaded proposals. */
  function descendantsOf(roots: Set<MConcept>): MConcept[] {
    return concepts.filter((q) => !q.dyingAt && !q.pending && !roots.has(q) && [...roots].some((r) => descends(q, r)));
  }

  /** An open proposal that names a doomed concept, a relation touching one, or a source, binding or attribute of the company. */
  function touchesCompany(q: MProposal, companyId: string, ids: Set<string>): boolean {
    if (q.companyId === companyId) return true;
    return touchesConcepts(q, ids);
  }

  function touchesConcepts(q: MProposal, ids: Set<string>): boolean {
    if (q.conceptId && ids.has(q.conceptId)) return true;
    for (const rid of [q.relationId, ...q.relationIds]) {
      const l = relationById(rid);
      if (l && (ids.has(l.aId) || ids.has(l.bId))) return true;
    }
    for (const bid of q.bindingIds) {
      const b = bindings.find((x) => x.id === bid);
      if (b && ids.has(b.conceptId)) return true;
    }
    if (q.attributeId && concepts.some((c) => ids.has(c.id) && c.attributes.some((a) => a.id === q.attributeId))) return true;
    return false;
  }

  /** Resolves a deletion target to the company and the concepts named directly (products expanded), refusing what the contract refuses. */
  function resolveTarget(target: T.DeletionTarget): { co: MCompany; named: MConcept[]; products: MDomain[] } {
    if (!target || typeof target !== 'object' || typeof target.companyId !== 'string') throw new Refusal(422, 'validation_failed', 'companyId is required');
    const co = companyOf(target.companyId);
    if (!co) throw new Refusal(404, 'not_found', 'company not found in this tenant');
    const conceptIds = target.conceptIds ?? [];
    const productIds = target.domainProductIds ?? [];
    if (!Array.isArray(conceptIds) || !Array.isArray(productIds)) throw new Refusal(422, 'validation_failed', 'conceptIds and domainProductIds are lists');
    if (conceptIds.length > BULK_CONCEPTS || productIds.length > BULK_PRODUCTS)
      throw new Refusal(422, 'validation_failed', `at most ${BULK_CONCEPTS} concepts and ${BULK_PRODUCTS} domain products`);
    if (new Set(conceptIds).size !== conceptIds.length || new Set(productIds).size !== productIds.length)
      throw new Refusal(422, 'validation_failed', 'ids are listed once');
    if (target.wholeCompany) {
      if (conceptIds.length || productIds.length) throw new Refusal(422, 'validation_failed', 'a whole company names no concepts or domain products');
      return { co, named: concepts.filter((c) => c.companyId === co.id && c.kind === 'concept' && !c.dyingAt && !c.pending), products: co.domains };
    }
    const named: MConcept[] = [];
    for (const id of conceptIds) {
      const c = conceptById(id);
      if (!c || c.dyingAt) throw new Refusal(404, 'not_found', 'concept not found in this tenant');
      if (c.companyId !== co.id) throw new Refusal(422, 'validation_failed', 'every concept belongs to the company');
      if (c.kind === 'root') throw new Refusal(409, 'root_concept', 'the company root cannot be deleted');
      named.push(c);
    }
    const products: MDomain[] = [];
    for (const id of productIds) {
      const d = domainById(id);
      if (!d) throw new Refusal(404, 'not_found', 'domain product not found in this tenant');
      if (d.companyId !== co.id) throw new Refusal(422, 'validation_failed', 'every domain product belongs to the company');
      products.push(d);
      for (const c of concepts) if (c.companyId === co.id && c.domainKey === d.key && !c.dyingAt && !c.pending && !named.includes(c)) named.push(c);
    }
    return { co, named, products };
  }

  /** `POST /deletion-impact`: what approving the deletion would remove. Pure. */
  function deletionImpact(target: T.DeletionTarget): T.DeletionImpact {
    const { co, named } = resolveTarget(target);
    const roots = new Set(named);
    const desc = descendantsOf(roots);
    const doomed = new Set<string>([...named, ...desc].map((c) => c.id));
    const rels = relations.filter((l) => !l.dyingAt && !l.pending && (doomed.has(l.aId) || doomed.has(l.bId)));
    const cross = rels.filter((l) => conceptById(l.aId)?.companyId !== conceptById(l.bId)?.companyId).length;
    const all = [...named, ...desc];
    const openTouching = open().filter((q) => (target.wholeCompany ? touchesCompany(q, co.id, doomed) : touchesConcepts(q, doomed))).length;
    return {
      concepts: named.length,
      descendants: desc.length,
      relations: rels.length,
      crossCompanyRelations: cross,
      bindings: all.filter((c) => c.bound && !c.bound.pending).length,
      attributes: all.reduce((n, c) => n + c.attributes.length, 0),
      sources: target.wholeCompany ? sources.filter((s) => s.companyId === co.id && !s.dyingAt).length : 0,
      cascadedProposals: openTouching,
      names: all.slice(0, IMPACT_NAMES).map((c) => c.label),
    };
  }

  /** The impact as proposal text: `3 concepts (A, B, C), 2 descendants, 5 relations (1 cross-company) …`. */
  function impactHtml(i: T.DeletionImpact, company: boolean): string {
    const n = (k: number, w: string) => `${k} ${w}${k === 1 ? '' : 's'}`;
    const parts = [
      `${n(i.concepts, 'concept')}${i.names.length ? ` (${i.names.map(e).join(', ')}${i.concepts + i.descendants > i.names.length ? ` and ${i.concepts + i.descendants - i.names.length} more` : ''})` : ''}`,
      n(i.descendants, 'descendant'),
      `${n(i.relations, 'relation')}${i.crossCompanyRelations ? ` (${i.crossCompanyRelations} cross-company)` : ''}`,
    ];
    if (company) parts.push(n(i.sources, 'source'));
    parts.push(n(i.bindings, 'binding'), n(i.attributes, 'attribute'));
    return parts.join(', ');
  }

  /** Marks concepts, their descendants and every touching relation dying, and rejects the open proposals touching them. */
  function purgeConcepts(p: Pick<MProposal, 'conceptId' | 'conceptIds' | 'relationIds'>, named: MConcept[]): void {
    const t = iso();
    const roots = new Set(named);
    const all = [...named, ...descendantsOf(roots)];
    const ids = new Set(all.map((c) => c.id));
    for (const q of open()) if (touchesConcepts(q, ids)) reject(q, []);
    for (const c of all) c.dyingAt = t;
    const rels = relations.filter((l) => !l.dyingAt && (ids.has(l.aId) || ids.has(l.bId)));
    for (const l of rels) l.dyingAt = t;
    p.conceptIds = all.map((c) => c.id).filter((id) => id !== p.conceptId);
    p.relationIds = rels.map((l) => l.id);
  }

  // ------------------------------------------------------------ domains

  /** A key from a name: lower case ASCII letters, digits and `_`, starting with a letter, unique in the tenant. */
  function keyFromName(name: string): T.DomainKey {
    let base = name
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 36);
    if (!/^[a-z]/.test(base)) base = `d_${base}`;
    if (base.length < 2) base = `${base}_1`;
    let key = base,
      n = 2;
    while (tenantDomain(key)) key = `${base}_${n++}`;
    return key;
  }

  function pCreateDomain(input: T.DomainInput): MProposal {
    checkName(input.name);
    if (!HEX.test(input.color || '')) throw new Refusal(422, 'validation_failed', 'color is a hex colour such as #3fb8a9');
    const owner = input.owner ?? '';
    if (owner.length > NAME_MAX || forbiddenText(owner)) throw new Refusal(422, 'validation_failed', 'owner holds at most 60 characters');
    if (domains.length >= MAX_DOMAINS) throw new Refusal(409, 'domain_limit', `a tenant holds at most ${MAX_DOMAINS} domains`);
    if (domains.some((d) => d.name.toLowerCase() === input.name.toLowerCase()))
      throw new Refusal(409, 'duplicate_label', `${input.name} is already a domain of the tenant`);
    const name = input.name,
      color = input.color.toLowerCase();
    return newProposal({
      type: 'change',
      changeKind: 'create_domain',
      title: `New domain ${name}`,
      heading: KIND_HEADING.change,
      color,
      companyId: null,
      domainId: null,
      parentLabel: null,
      deps: [],
      ready: () => true,
      waitFor: null,
      html: `New domain <b>${e(name)}</b>${owner ? ` <em>· owned by ${e(owner)}</em>` : ''}`,
      why: 'tenant-wide: available to every company once approved',
      caption: `${name} is a domain of every company now.`,
      conceptId: null,
      relationId: null,
      relationIds: [],
      sourceId: null,
      bindingIds: [],
      attributeId: null,
      apply() {
        if (domains.length >= MAX_DOMAINS) throw new Refusal(409, 'domain_limit', `a tenant holds at most ${MAX_DOMAINS} domains`);
        if (domains.some((d) => d.name.toLowerCase() === name.toLowerCase()))
          throw new Refusal(409, 'duplicate_label', `${name} is already a domain of the tenant`);
        const taken = new Set(domains.map((d) => d.position));
        let position = DOMAIN_TEMPLATES.length;
        while (taken.has(position)) position++;
        const d: MTenantDomain = { key: keyFromName(name), name, owner, defaultColor: color, template: false, position, revision: 0 };
        domains.push(d);
        emit('domain.changed', { domain: toTenantDomain(d), created: true });
      },
    });
  }

  function pEditDomain(key: string, patch: T.DomainPatch): MProposal {
    const d = tenantDomain(key);
    if (!d) throw new Refusal(404, 'not_found', 'domain not found in this tenant');
    const fields = ['name', 'color', 'owner'] as const;
    const given = fields.filter((k) => patch[k] !== undefined);
    if (!given.length) throw new Refusal(422, 'validation_failed', 'name, color or owner is required');
    if (patch.name !== undefined) {
      checkName(patch.name);
      if (domains.some((x) => x !== d && x.name.toLowerCase() === (patch.name as string).toLowerCase()))
        throw new Refusal(409, 'duplicate_label', `${patch.name} is already a domain of the tenant`);
    }
    if (patch.color !== undefined && !HEX.test(patch.color)) throw new Refusal(422, 'validation_failed', 'color is a hex colour such as #3fb8a9');
    if (patch.owner !== undefined && (patch.owner.length > NAME_MAX || forbiddenText(patch.owner)))
      throw new Refusal(422, 'validation_failed', 'owner holds at most 60 characters');
    const name = patch.name,
      color = patch.color?.toLowerCase(),
      owner = patch.owner;
    const what = [
      name !== undefined ? `rename to <b>${e(name)}</b>` : '',
      color !== undefined ? `colour <b>${e(color)}</b>` : '',
      owner !== undefined ? `owner <b>${e(owner)}</b>` : '',
    ]
      .filter(Boolean)
      .join(', ');
    return newProposal({
      type: 'change',
      changeKind: 'edit_domain',
      title: `Edit domain ${d.name}`,
      heading: KIND_HEADING.change + ` · ${d.name}`,
      color: color ?? (appearance.colors[d.key] || d.defaultColor),
      companyId: null,
      domainId: null,
      parentLabel: null,
      deps: [],
      ready: () => true,
      waitFor: null,
      html: `Domain <b>${e(d.name)}</b>: ${what}`,
      why: 'tenant-wide: every company sees the change',
      caption: `${name ?? d.name} changed in every company.`,
      conceptId: null,
      relationId: null,
      relationIds: [],
      sourceId: null,
      bindingIds: [],
      attributeId: null,
      apply() {
        if (name !== undefined && domains.some((x) => x !== d && x.name.toLowerCase() === name.toLowerCase()))
          throw new Refusal(409, 'duplicate_label', `${name} is already a domain of the tenant`);
        if (name !== undefined) d.name = name;
        if (owner !== undefined) d.owner = owner;
        if (color !== undefined) appearance.colors[d.key] = color;
        d.revision += 1;
        this.domainIds = companies.map((c) => c.domains.find((x) => x.key === d.key)?.id).filter((x): x is string => !!x);
        emit('domain.changed', { domain: toTenantDomain(d), created: false });
        if (color !== undefined) emit('appearance.changed', { appearance: toAppearance() });
      },
    });
  }

  function pDeleteDomain(productId: string): MProposal {
    const d = domainById(productId);
    if (!d) throw new Refusal(404, 'not_found', 'domain product not found in this tenant');
    const co = companyOf(d.companyId) as MCompany;
    const impact = deletionImpact({ companyId: co.id, domainProductIds: [d.id] });
    return newProposal({
      type: 'change',
      changeKind: 'delete_domain',
      title: `Delete ${nameOf(d)} of ${co.name}`,
      heading: KIND_HEADING.change + ` · ${nameOf(d)}`,
      color: C.conflict,
      companyId: co.id,
      domainId: d.id,
      parentLabel: null,
      deps: [],
      ready: () => true,
      waitFor: null,
      html: `Delete <b>${e(nameOf(d))}</b> of ${e(co.name)} with its ${impactHtml(impact, false)}`,
      why: 'the domain itself stays available to every company',
      caption: `${nameOf(d)} of ${co.name} was emptied.`,
      conceptId: null,
      relationId: null,
      relationIds: [],
      sourceId: null,
      bindingIds: [],
      attributeId: null,
      apply() {
        purgeConcepts(this, concepts.filter((c) => c.companyId === co.id && c.domainKey === d.key && !c.dyingAt));
      },
    });
  }

  function pMoveConcept(conceptId: string, key: string): MProposal {
    const c = conceptById(conceptId);
    if (!c || c.dyingAt) throw new Refusal(404, 'not_found', 'concept not found in this tenant');
    if (c.kind === 'root') throw new Refusal(409, 'root_concept', 'the company root has no domain');
    if (c.pending) throw new Refusal(409, 'concept_pending', `${c.label} is awaiting approval`);
    const td = tenantDomain(key);
    if (!td) throw new Refusal(422, 'validation_failed', `${key} is not a domain of the tenant`);
    if (c.domainKey === td.key) throw new Refusal(422, 'validation_failed', `${c.label} is already in ${td.name}`);
    const from = domainOfConcept(c);
    return newProposal({
      type: 'change',
      changeKind: 'move_concept_domain',
      title: `Move ${c.label} to ${td.name}`,
      heading: KIND_HEADING.change + ` · ${td.name}`,
      color: domainColour(td.key),
      companyId: c.companyId,
      domainId: from ? from.id : null,
      parentLabel: null,
      deps: [],
      ready: () => true,
      waitFor: null,
      html: `Move <b>${e(c.label)}</b> from <em>${e(from ? nameOf(from) : 'the company')}</em> to <em>${e(td.name)}</em>`,
      why: 'children, relations and bindings stay as they are',
      caption: `${c.label} is kept in ${td.name} now.`,
      conceptId: c.id,
      relationId: null,
      relationIds: [],
      sourceId: null,
      bindingIds: [],
      attributeId: null,
      apply() {
        const to = ensureProduct(c.companyId, td.key);
        if (!to) throw new Refusal(422, 'validation_failed', `${td.key} is not a domain of the tenant`);
        c.domainKey = td.key;
        to.revision += 1;
        this.domainIds = [to.id];
      },
    });
  }

  function pBulkDelete(body: T.BulkDeleteRequest): MProposal {
    const { co, named, products } = resolveTarget({ companyId: body.companyId, conceptIds: body.conceptIds, domainProductIds: body.domainProductIds });
    if (!(body.conceptIds ?? []).length && !(body.domainProductIds ?? []).length)
      throw new Refusal(422, 'validation_failed', 'conceptIds or domainProductIds is required');
    const impact = deletionImpact({ companyId: co.id, conceptIds: body.conceptIds, domainProductIds: body.domainProductIds });
    const nc = (body.conceptIds ?? []).length,
      nd = products.length;
    const what = [nc ? `${nc} concept${nc === 1 ? '' : 's'}` : '', nd ? `${nd} domain product${nd === 1 ? '' : 's'}` : ''].filter(Boolean).join(' and ');
    return newProposal({
      type: 'change',
      changeKind: 'delete_bulk',
      title: `Delete ${what}`,
      heading: KIND_HEADING.change,
      color: C.conflict,
      companyId: co.id,
      domainId: null,
      parentLabel: null,
      deps: [],
      ready: () => true,
      waitFor: null,
      html: `Delete ${e(what)} of ${e(co.name)}: ${impactHtml(impact, false)}`,
      why: 'all or nothing on approval',
      caption: `${what} left ${co.name}.`,
      conceptId: null,
      relationId: null,
      relationIds: [],
      sourceId: null,
      bindingIds: [],
      attributeId: null,
      apply() {
        purgeConcepts(this, named.filter((c) => !c.dyingAt));
        this.domainIds = products.map((d) => d.id);
      },
    });
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
        const n = conceptById(draft.conceptId) || (draft.conceptLabel && draft.companyId ? findConcept(draft.conceptLabel, draft.companyId) : null);
        if (!n) throw new Refusal(404, 'concept_not_found', 'concept does not exist');
        if (draft.value !== undefined) return pTaught(n, draft.name, draft.attributeType, draft.value);
        return pAttr(n, [draft.name, draft.attributeType, draft.col ?? '', draft.fill ?? 0, 'new'], draft.sourceId ?? null);
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

  function approve(p: MProposal, bulk: boolean, cascade: MProposal[] = [], expectedRevision?: number): T.DecisionResult {
    if (expectedRevision !== undefined && expectedRevision !== p.revision)
      throw new Refusal(409, 'proposal_changed', `${p.title} was edited since you read it`);
    if (!p.ready()) throw new Refusal(409, 'proposal_not_ready', `${p.title} waits for ${p.waitFor || 'a previous item'}`);
    if (settings.twoApprovers && p.type === 'change' && !p.second) {
      p.second = true;
      p.state = 'half_approved';
      p.why = (p.why ? p.why + ' · ' : '') + '1 of 2 approvals · a Governor must approve too';
      const entry = addProposalAudit(p, `${p.title} · 1 of 2`, true);
      const result = decision(p, [], entry);
      emit('proposal.half_approved', { proposal: result.proposal, artefacts: result.artefacts, cascaded: [] }, bulk);
      return result;
    }
    p.state = 'approved';
    p.decidedAt = iso();
    const entry = addProposalAudit(p, p.title, true);
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
    if (p.changeKind === 'edit_domain' || p.changeKind === 'delete_bulk') for (const d of (p.domainIds || []).map(domainById)) if (d) d.revision += 1;
    const result = decision(p, cascade, entry, p.caption ?? undefined);
    emit('proposal.approved', { ...result, audit: undefined }, bulk);
    afterApply();
    return result;
  }

  function reject(p: MProposal, cascaded: MProposal[]): T.DecisionResult {
    p.state = 'rejected';
    p.decidedAt = iso();
    const entry = addProposalAudit(p, p.title, false);
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
      for (const q of open()) {
        if (q.state !== 'pending' && q.state !== 'half_approved') continue;
        if (q.type === 'attr' && c.attributes.some((a) => a.id === q.attributeId)) {
          reject(q, cascaded);
          cascaded.push(q);
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

  // ------------------------------------------------------------ fixture

  /** The dev and test fixture: the home company's root cell and nothing else. */
  function reset(): void {
    companies = [];
    concepts = [];
    sources = [];
    relations = [];
    bindings = [];
    proposals = [];
    audit = [];
    imports = [];
    expansions = [];
    extractions = [];
    coverage = false;
    appearance.theme = 'dark';
    appearance.colors = {};
    appearance.accent = '#3fb8a9';
    appearance.source = DEFAULT_BRASS;
    domains = DOMAIN_TEMPLATES.map((t, position) => ({ key: t.key, name: t.name, owner: t.owner, defaultColor: t.color, template: true, position, revision: 0 }));
    addCompany(HOME_COMPANY.name, HOME_COMPANY.sub);
  }

  function createCompany(body: T.CompanyCreate): T.CompanyCreated {
    if (!settings.companyCreation) throw new Refusal(409, 'company_creation_disabled', 'company creation is disabled in the admin portal');
    if (!body?.name?.trim()) throw new Refusal(422, 'name_required', 'a company needs a name');
    const c = addCompany(body.name.trim(), (body.sub || '').trim());
    const root = conceptById(c.rootId) as MConcept;
    emit('company.created', { company: toCompany(c), root: toConcept(root) });
    const made: MProposal[] = [];
    if (body.start === 'starter_vocabulary') {
      for (const [label, dom, pred, parent] of SEED) {
        const host = findConcept(parent || c.name, c.id);
        if (!host) continue;
        const domName = tenantDomain(dom)?.name;
        let seed: number | undefined;
        if (hooks.rememberBirth) {
          const draws: MockBirth = { noise: random(), node: random() * 100, link: random() };
          hooks.rememberBirth(c.id, label, draws);
          seed = draws.link;
        }
        const p = pConcept(host, label, dom, pred, `${label} is kept in ${c.name}’s ${domName}.`, false, seed);
        made.push(p);
        emit('proposal.created', { proposal: toProposal(p), artefacts: artefactsOf(p), cascaded: [] });
      }
    }
    addAudit('company', `${c.name} added`, true, null, [c.id]);
    return { company: toCompany(c), root: toConcept(root), proposals: made.map(toProposal) };
  }

  reset();

  // ------------------------------------------------------------ teaching

  /** The lines of `POST /teach/parse/stream` for a parse the grammar answers whole: each draft, then the result. */
  function streamedParse(result: T.TeachResult): T.TeachStreamEvent[] {
    const drafts: T.TeachStreamEvent[] = result.drafts.map((draft, index) => ({ type: 'draft', index, draft, note: result.draftNotes[index] }));
    return [...drafts, { type: 'result', result }];
  }

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

  /**
   * The port of the reference's `teach` on its import path: intents to drafts, without writing
   * anything to the model. The sentence is typed text, a speech transcript, or a stored import
   * sentence cited by `importRef`, whose text is read from the import; each draft carries the
   * request's origin and import reference.
   */
  function teachParse(body: T.TeachRequest): T.TeachResult {
    const co = companyOf(body.companyId);
    if (!co) throw new Refusal(404, 'not_found', 'company not found in this tenant');
    let text0: string;
    let origin: T.Origin;
    let originDetail: T.OriginDetail | null = null;
    if (body.importRef) {
      if (!settings.importDocs) throw new Refusal(409, 'channel_disabled', 'document import is disabled in the admin portal');
      const { imp, index } = citedSentence(body.importRef);
      if (imp.parseCounts[index] >= IMPORT_PARSES_PER_SENTENCE)
        throw new Refusal(409, 'import_sentence_used', 'this sentence was already parsed three times');
      imp.parseCounts[index]++;
      text0 = imp.sentences[index];
      origin = 'document';
      originDetail = detailOf(imp, index);
    } else {
      origin = body.origin === 'speech' ? 'speech' : 'text';
      if (!settings.liveTeaching) throw new Refusal(409, 'channel_disabled', 'live teaching is disabled in the admin portal');
      if (origin === 'speech' && !settings.voice) throw new Refusal(409, 'channel_disabled', 'voice input is disabled in the admin portal');
      text0 = (body.text || '').trim();
      if (!text0) throw new Refusal(422, 'validation_failed', 'a sentence is needed');
    }
    const declared = origin;
    const stamp = <D extends T.ProposalDraft>(d: D): D =>
      body.importRef ? { ...d, importRef: body.importRef } : { ...d, origin: declared as T.InputOrigin };
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
      return {
        outcome: 'understood',
        domainKey: (domKey as T.DomainKey) || null,
        intents,
        drafts: drafts.map(stamp),
        statements: made,
        caption: made.join(' · ') + '. Waiting for your approval on the right.',
        origin,
        originDetail,
        extractor: 'rules',
        degraded: false,
        llmOutcome: 'not_triggered',
        draftNotes: drafts.map(() => ({ extractor: 'rules', confidence: 1 })),
        unresolved: [],
        segments: [{ index: 0, span: { start: 0, end: Array.from(text0).length } }],
      };
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
        origin,
        originDetail,
        extractor: 'rules',
        degraded: false,
        llmOutcome: 'not_triggered',
        draftNotes: [],
        unresolved: [],
        segments: [{ index: 0, span: { start: 0, end: Array.from(text0).length } }],
      };
    return {
      outcome: 'partly_understood',
      domainKey: (domKey as T.DomainKey) || null,
      intents,
      drafts: fresh.map((w) =>
        stamp({ type: 'concept' as const, companyId: co.id, parentId: host.id, label: title(w), domainKey: key(host.domainKey), action: 'relates to', caption: `${title(w)} is kept.` }),
      ),
      statements: [],
      caption: `No action found; ${fresh.map(title).join(', ')} proposed from ${host.label} with “relates to”. Click the line to give it the right action.`,
      origin,
      originDetail,
      extractor: 'rules',
      degraded: false,
      llmOutcome: 'not_triggered',
      draftNotes: fresh.map(() => ({ extractor: 'rules', confidence: 1 })),
      unresolved: [],
      segments: [{ index: 0, span: { start: 0, end: Array.from(text0).length } }],
    };
  }

  // ------------------------------------------------------------ document imports

  /** The stored import and sentence a reference cites: 404 when unknown, 410 past its expiry. */
  function citedSentence(ref: T.ImportRef): { imp: MImport; index: number } {
    const imp = imports.find((x) => x.id === ref?.importId);
    if (!imp) throw new Refusal(404, 'not_found', 'import not found in this tenant');
    if (nowDate().getTime() >= imp.expiresAt) throw new Refusal(410, 'import_expired', 'the import has expired; import the document again');
    const index = ref.sentenceIndex;
    if (!Number.isInteger(index) || index < 0 || index >= imp.sentences.length)
      throw new Refusal(404, 'not_found', 'sentence not found in this import');
    return { imp, index };
  }

  function detailOf(imp: MImport, index: number): T.OriginDetail {
    const position = imp.positions[index];
    return { fileName: imp.fileName, mediaType: imp.mediaType, sentenceIndex: index, ...(position ? { position } : {}) };
  }

  /**
   * Provenance of every draft of one proposal call, checked before anything is created: a draft's
   * own origin and import reference win over the call's. A cited sentence is claimed once per
   * call; `claim` marks the claims when the call succeeds.
   */
  function provenanceOf(drafts: T.ProposalDraft[], batch: { origin?: T.InputOrigin; importRef?: T.ImportRef } = {}) {
    const claimed = new Map<string, { imp: MImport; index: number }>();
    const each = drafts.map((d) => {
      const ref = d.importRef ?? batch.importRef;
      if (ref) {
        if (!settings.importDocs) throw new Refusal(409, 'channel_disabled', 'document import is disabled in the admin portal');
        const cited = citedSentence(ref);
        const key = `${cited.imp.id}|${cited.index}`;
        if (!claimed.has(key)) {
          if (cited.imp.drafted[cited.index]) throw new Refusal(409, 'import_sentence_used', 'this sentence was already drafted');
          claimed.set(key, cited);
        }
        return { origin: 'document' as T.Origin, originDetail: detailOf(cited.imp, cited.index) as T.OriginDetail | null };
      }
      const origin: T.Origin = (d.origin ?? batch.origin) === 'speech' ? 'speech' : 'text';
      if (origin === 'speech' && !settings.voice) throw new Refusal(409, 'channel_disabled', 'voice input is disabled in the admin portal');
      return { origin, originDetail: null as T.OriginDetail | null };
    });
    const claim = () => {
      for (const { imp, index } of claimed.values()) imp.drafted[index] = true;
    };
    return { each, claim };
  }

  /** Creates drafts in order under their provenance; the import claims land only when all succeed. */
  function createDrafts(drafts: T.ProposalDraft[], batch?: { origin?: T.InputOrigin; importRef?: T.ImportRef }): T.Proposal[] {
    refuseMixedDrafts(drafts);
    const { each, claim } = provenanceOf(drafts, batch);
    const outs: T.Proposal[] = [];
    try {
      drafts.forEach((d, i) => {
        provenance = each[i];
        const p = createFromDraft(d, []);
        const out = toProposal(p);
        emit('proposal.created', { proposal: out, artefacts: out.artefacts, cascaded: [] });
        outs.push(out);
      });
    } finally {
      provenance = { origin: 'text', originDetail: null };
    }
    claim();
    return outs;
  }

  /** Validates, extracts and stores an uploaded document, as `POST /import/sentences` does. */
  async function importDocument(file: { name: string; type: string; bytes: Uint8Array }, fields: Record<string, string> = {}): Promise<MockResponse> {
    try {
      if (!settings.importDocs) throw new Refusal(409, 'channel_disabled', 'document import is disabled in the admin portal');
      const extracted = await extractDocument(file.name, file.type, file.bytes, fields.mediaType || undefined);
      const imp: MImport = {
        id: uuid(),
        fileName: extracted.fileName,
        mediaType: extracted.mediaType,
        sentences: extracted.sentences.map((x) => x.text),
        positions: extracted.sentences.map((x) => x.position),
        parseCounts: extracted.sentences.map(() => 0),
        drafted: extracted.sentences.map(() => false),
        expiresAt: nowDate().getTime() + IMPORT_LIFETIME_MS,
      };
      imports.push(imp);
      return json(200, {
        importId: imp.id,
        expiresAt: new Date(imp.expiresAt).toISOString(),
        fileName: imp.fileName,
        origin: 'document',
        originDetail: { fileName: imp.fileName, mediaType: imp.mediaType },
        sentences: imp.sentences,
        skipped: extracted.skipped,
        positions: imp.positions,
      } satisfies T.ImportResult);
    } catch (e) {
      if (e instanceof Refusal) return problem(e);
      if (e instanceof ExtractRefusal) return problem(new Refusal(e.status, e.code, e.detail));
      throw e;
    }
  }

  /** Detects whether an upload is a document or an ontology, as `POST /import/detect` does. */
  async function detectImport(file: { name: string; type: string; bytes: Uint8Array }): Promise<MockResponse> {
    try {
      if (!settings.importDocs) throw new Refusal(409, 'channel_disabled', 'document import is disabled in the admin portal');
      return json(200, await detectFile(file));
    } catch (e) {
      if (e instanceof Refusal) return problem(e);
      if (e instanceof ExtractRefusal) return problem(new Refusal(e.status, e.code, e.detail));
      throw e;
    }
  }

  // ------------------------------------------------------------ branch approval

  function isOpen(p: MProposal): boolean {
    return p.state === 'pending' || p.state === 'half_approved';
  }

  /**
   * A proposal's open branch: the open concept and spec proposals born under it at any depth,
   * then the open relation proposals whose ends are both in the branch or approved, at least one
   * of them in the branch. Dependencies resolve inside the root's company only.
   */
  function branchOf(root: MProposal): MProposal[] {
    if ((root.type !== 'concept' && root.type !== 'spec') || !root.conceptId || !isOpen(root) || !root.companyId) return [];
    const companyId = root.companyId;
    const inBranch = new Set<string>([root.conceptId]);
    const members: MProposal[] = [];
    let grew = true;
    while (grew) {
      grew = false;
      for (const q of open()) {
        if (q === root || members.includes(q) || (q.type !== 'concept' && q.type !== 'spec') || !q.conceptId) continue;
        if (q.companyId !== companyId || !q.parentLabel) continue;
        const parent = findConcept(q.parentLabel, companyId);
        if (parent && inBranch.has(parent.id)) {
          members.push(q);
          inBranch.add(q.conceptId);
          grew = true;
        }
      }
    }
    for (const q of open()) {
      if (q.type !== 'relation' || q.companyId !== companyId) continue;
      const l = relationById(q.relationId);
      const ends = l ? [conceptById(l.aId), conceptById(l.bId)] : [];
      if (ends.length !== 2 || ends.some((c) => !c || c.companyId !== companyId)) continue;
      const inside = ends.filter((c) => c && inBranch.has(c.id)).length;
      if (inside && ends.every((c) => c && (inBranch.has(c.id) || !c.pending))) members.push(q);
    }
    return members;
  }

  function approveBranch(root: MProposal): T.BranchResult {
    if (!isOpen(root)) throw new Refusal(409, 'proposal_decided', 'already decided');
    if (root.type !== 'concept' && root.type !== 'spec')
      throw new Refusal(409, 'branch_root_invalid', 'a branch starts at a concept or specialisation proposal');
    let approved = 0,
      batches = 0;
    const members = [root, ...branchOf(root)];
    while (batches < 50) {
      const ready = members.filter((p) => isOpen(p) && p.ready());
      if (!ready.length) break;
      for (const p of ready) {
        approve(p, true);
        approved++;
      }
      batches++;
    }
    const remaining = members.filter(isOpen).length;
    return { rootId: root.id, approved, skipped: 0, remaining, batches, complete: true };
  }

  // ------------------------------------------------------------ concept expansion

  interface MExpansion {
    id: string;
    companyId: string;
    drafts: T.ExpansionDraft[];
    notes: T.ExpansionNote[];
    expiresAt: number;
    submitted: boolean;
  }
  const EXPANSION_LIFETIME_MS = 60 * 60 * 1000;
  /** The mock model's suggestions: each child is the expanded label with one suffix, action and rationale. */
  const SUGGESTED: [string, string, string][] = [
    ['planning', 'includes', 'Planning decides what it needs next'],
    ['records', 'keeps', 'Records hold what happened'],
    ['team', 'is run by', 'A team is accountable for it'],
  ];

  function expand(conceptId: string, body: T.ExpansionRequest): T.ExpansionResult {
    const c = conceptById(conceptId);
    if (!c || c.dyingAt) throw new Refusal(404, 'not_found', 'concept not found in this tenant');
    if (c.pending) throw new Refusal(409, 'concept_pending', `${c.label} is awaiting approval`);
    const focus = body?.focus;
    if (focus !== undefined && (typeof focus !== 'string' || !focus.length || focus.length > 200 || /[<>\u0000-\u001f]/.test(focus)))
      throw new Refusal(422, 'validation_failed', 'focus holds 1 to 200 characters without markup or control characters');
    for (const k of ['depth', 'maxChildren'] as const) {
      const v = body?.[k];
      if (v !== undefined && (!Number.isInteger(v) || v < 1)) throw new Refusal(422, 'validation_failed', `${k} is a whole number of at least 1`);
    }
    const empty = (llmOutcome: T.ExpansionOutcome, skipped: T.ExpansionSkip[] = []): T.ExpansionResult => ({
      expansionId: null,
      expiresAt: null,
      conceptId,
      llmOutcome,
      degraded: llmOutcome !== 'used',
      drafts: [],
      notes: [],
      skipped,
    });
    if (settings.llmMonthlyTokenCap === 0) return empty('budget_exhausted');
    const domainKey = (c.domainKey || 'production') as T.DomainKey;
    const deep = (body?.depth ?? 2) >= 2;
    const drafts: T.ExpansionDraft[] = [];
    const notes: T.ExpansionNote[] = [];
    const skipped: T.ExpansionSkip[] = [];
    const children: number[] = [];
    SUGGESTED.slice(0, body?.maxChildren ?? SUGGESTED.length).forEach(([suffix, action, rationale], i) => {
      const label = title(`${c.label} ${suffix}`);
      const grandchild = title(`${c.label} schedule`);
      if (findConcept(label, c.companyId)) {
        skipped.push({ label, reason: 'existing_label' });
        if (i === 0 && deep) skipped.push({ label: grandchild, reason: 'parent_skipped' });
        return;
      }
      children.push(drafts.length);
      drafts.push({ type: 'concept', companyId: c.companyId, parentId: c.id, label, domainKey, action, reverse: false });
      notes.push({ confidence: 0.9 - i * 0.1, rationale, depth: 1, requires: [] });
      if (i !== 0 || !deep) return;
      if (findConcept(grandchild, c.companyId)) {
        skipped.push({ label: grandchild, reason: 'existing_label' });
        return;
      }
      drafts.push({ type: 'concept', companyId: c.companyId, parentLabel: label, label: grandchild, domainKey, action: 'produces', reverse: false });
      notes.push({ confidence: 0.72, rationale: 'Planning produces a schedule', depth: 2, requires: [drafts.length - 2] });
    });
    if (children.length >= 3) {
      const [a, b] = [children[1], children[2]];
      const aLabel = (drafts[a] as T.ConceptDraft).label,
        bLabel = (drafts[b] as T.ConceptDraft).label;
      drafts.push({ type: 'relation', companyId: c.companyId, aLabel, bLabel, action: 'is kept by' });
      notes.push({ confidence: 0.6, rationale: 'The team keeps the records', depth: null, requires: [a, b] });
    }
    if (!drafts.length) return empty('used', skipped);
    const x: MExpansion = { id: uuid(), companyId: c.companyId, drafts, notes, expiresAt: nowDate().getTime() + EXPANSION_LIFETIME_MS, submitted: false };
    expansions.push(x);
    return { expansionId: x.id, expiresAt: new Date(x.expiresAt).toISOString(), conceptId, llmOutcome: 'used', degraded: false, drafts, notes, skipped };
  }

  /** The selected indexes in draft order, refused unless distinct, in range and closed under `requires`. */
  function selection(indexes: unknown, notes: { requires: number[] }[]): number[] {
    if (!Array.isArray(indexes) || !indexes.length) throw new Refusal(422, 'validation_failed', 'indexes needs at least one draft');
    const chosen = new Set<number>();
    for (const i of indexes) {
      if (!Number.isInteger(i) || i < 0 || i >= notes.length || chosen.has(i))
        throw new Refusal(422, 'validation_failed', 'indexes are distinct draft indexes');
      chosen.add(i);
    }
    for (const i of chosen)
      for (const r of notes[i].requires) if (!chosen.has(r)) throw new Refusal(422, 'validation_failed', `draft ${i} requires draft ${r}`);
    return [...chosen].sort((a, b) => a - b);
  }

  /** Creates the chosen stored drafts in draft order, each under its provenance; a relation's label ends resolve in the company. */
  function proposeStored(
    drafts: (T.ProposalDraft | T.ExpansionDraft)[],
    chosen: number[],
    companyId: string,
    origin: (i: number) => { origin: T.Origin; originDetail: T.OriginDetail | null },
    each: (i: number, p: MProposal) => void = () => undefined,
  ): T.Proposal[] {
    for (const i of chosen) {
      const d = drafts[i];
      if ((d.type === 'concept' || d.type === 'spec') && findConcept(d.label, companyId))
        throw new Refusal(409, 'duplicate_label', `${d.label} already exists in this company`);
    }
    const outs: T.Proposal[] = [];
    try {
      for (const i of chosen) {
        const d = drafts[i];
        provenance = origin(i);
        let draft = d as T.ProposalDraft;
        if (d.type === 'relation') {
          const a = conceptById(d.aId) || (d.aLabel ? findConcept(d.aLabel, companyId) : null);
          const b = conceptById(d.bId) || (d.bLabel ? findConcept(d.bLabel, companyId) : null);
          draft = { ...d, aId: a?.id ?? '', bId: b?.id ?? '' };
        }
        const p = createFromDraft(draft, []);
        each(i, p);
        const out = toProposal(p);
        emit('proposal.created', { proposal: out, artefacts: out.artefacts, cascaded: [] });
        outs.push(out);
      }
    } finally {
      provenance = { origin: 'text', originDetail: null };
    }
    return outs;
  }

  function proposeExpansion(id: string, body: { indexes?: unknown }): T.Proposal[] {
    const x = expansions.find((y) => y.id === id);
    if (!x) throw new Refusal(404, 'not_found', 'expansion not found in this tenant');
    if (nowDate().getTime() >= x.expiresAt) throw new Refusal(410, 'expansion_expired', 'the expansion has expired; expand again');
    if (x.submitted) throw new Refusal(409, 'expansion_submitted', 'the expansion was already proposed');
    const chosen = selection(body?.indexes, x.notes);
    const outs = proposeStored(
      x.drafts,
      chosen,
      x.companyId,
      () => ({ origin: 'suggestion', originDetail: null }),
      (i, p) => {
        const n = x.notes[i];
        p.heading = `${p.heading} · suggested`;
        p.why = `Suggested by the model · ${Math.round(n.confidence * 100)}% · ${n.rationale}`;
      },
    );
    x.submitted = true;
    return outs;
  }

  // ------------------------------------------------------------ whole-document extraction

  interface MExtraction {
    job: T.DocumentExtraction;
    imp: MImport;
    result: T.DocumentExtractionResult | null;
  }
  const RESULT_LIFETIME_MS = 24 * 60 * 60 * 1000;

  function startExtraction(importId: string, body: { companyId?: string }): T.DocumentExtraction {
    if (!settings.importDocs) throw new Refusal(409, 'channel_disabled', 'document import is disabled in the admin portal');
    const imp = imports.find((x) => x.id === importId);
    if (!imp) throw new Refusal(404, 'not_found', 'import not found in this tenant');
    if (nowDate().getTime() >= imp.expiresAt) throw new Refusal(410, 'import_expired', 'the import has expired; import the file again');
    const co = companyOf(body?.companyId || '');
    if (!co) throw new Refusal(404, 'not_found', 'company not found in this tenant');
    if (extractions.some((x) => x.imp === imp)) throw new Refusal(409, 'extraction_exists', 'this import already has an extraction job');
    if (extractions.some((x) => x.job.state === 'queued' || x.job.state === 'running'))
      throw new Refusal(409, 'extraction_running', 'another extraction job of yours is still running');
    const job: T.DocumentExtraction = {
      id: uuid(),
      importId,
      companyId: co.id,
      state: 'queued',
      phase: null,
      chunks: 1,
      outlineChunksDone: 0,
      sectionChunksDone: 0,
      outlineNodes: 0,
      tokensUsed: 0,
      tokenCeiling: 1_000_000,
      nodeCeiling: 2000,
      draftCount: 0,
      degraded: false,
      failureReason: null,
      cancelRequested: false,
      createdAt: iso(),
      startedAt: null,
      finishedAt: null,
      expiresAt: null,
      submittedAt: null,
    };
    extractions.push({ job, imp, result: null });
    emit('extraction.changed', { extraction: { ...job } });
    return { ...job };
  }

  function extractionOf(id: string): MExtraction {
    const x = extractions.find((y) => y.job.id === id);
    if (!x) throw new Refusal(404, 'not_found', 'extraction not found in this tenant');
    return x;
  }

  /** The mock job moves one step per read: from queued to running its sections, then to its end. */
  function readExtraction(id: string): T.DocumentExtraction {
    const x = extractionOf(id);
    const job = x.job;
    if (job.state === 'queued') {
      Object.assign(job, { state: 'running', phase: 'sections', startedAt: iso(), outlineChunksDone: job.chunks, tokensUsed: 900 });
      emit('extraction.changed', { extraction: { ...job } });
    } else if (job.state === 'running') {
      finishExtraction(x);
      emit('extraction.changed', { extraction: { ...job } });
    }
    return { ...job };
  }

  function finishExtraction(x: MExtraction): void {
    const job = x.job;
    const done = { phase: null, finishedAt: iso(), sectionChunksDone: job.chunks };
    if (settings.llmMonthlyTokenCap === 0) {
      Object.assign(job, done, { state: 'failed', failureReason: 'budget_exhausted' });
      return;
    }
    const result = mapDocument(x.imp, job);
    if (!result.drafts.length) {
      Object.assign(job, done, { state: 'failed', failureReason: 'no_drafts' });
      return;
    }
    x.result = result;
    Object.assign(job, done, {
      state: 'succeeded',
      draftCount: result.drafts.length,
      outlineNodes: result.outline.length,
      expiresAt: new Date(nowDate().getTime() + RESULT_LIFETIME_MS).toISOString(),
    });
  }

  /** The mock's reading of a whole document: the intents of every sentence as one tree under the company root. */
  function mapDocument(imp: MImport, job: T.DocumentExtraction): T.DocumentExtractionResult {
    const co = companyOf(job.companyId) as MCompany;
    const drafts: T.ProposalDraft[] = [];
    const notes: T.DocumentDraftNote[] = [];
    const outline: T.OutlineNode[] = [];
    const drafted = new Map<string, number>();
    imp.sentences.forEach((sentence, sentenceIndex) => {
      for (const it of understand(sentence)) {
        if (it.kind !== 'rel') continue;
        const place = (label: string, parent: string | null, action: string): void => {
          const key = label.toLowerCase();
          if (drafted.has(key) || findConcept(label, co.id)) return;
          const parentIndex = parent ? drafted.get(parent.toLowerCase()) : undefined;
          const host = (parent && findConcept(parent, co.id)) || conceptById(co.rootId);
          const depth = parentIndex !== undefined ? (notes[parentIndex].depth ?? 0) + 1 : 1;
          const role: T.OutlineRole = depth === 1 ? 'process' : 'step';
          const base = { type: 'concept' as const, companyId: co.id, label, domainKey: 'production' as T.DomainKey, action };
          drafted.set(key, drafts.length);
          drafts.push(
            (parentIndex !== undefined ? { ...base, parentLabel: parent } : { ...base, parentId: host?.id ?? co.rootId }) as T.ProposalDraft,
          );
          notes.push({ pass: 'outline', confidence: 0.9, role, depth, requires: parentIndex !== undefined ? [parentIndex] : [], sentenceIndex });
          outline.push({ index: outline.length, parentIndex: parentIndex ?? null, conceptId: null, label, role, depth, sentenceIndex });
        };
        place(title(it.subj), null, 'has');
        place(title(it.obj), title(it.subj), it.pred || 'relates to');
      }
    });
    return { extractionId: job.id, outline, drafts, notes, unresolved: [] };
  }

  function extractionResult(id: string): T.DocumentExtractionResult {
    const x = extractionOf(id);
    if (x.job.state !== 'succeeded' || !x.result) throw new Refusal(409, 'extraction_not_ready', 'the job has not succeeded');
    if (x.job.expiresAt && nowDate().getTime() >= Date.parse(x.job.expiresAt)) throw new Refusal(410, 'extraction_expired', 'the result has expired');
    return x.result;
  }

  function proposeExtraction(id: string, body: { indexes?: unknown }): T.Proposal[] {
    const x = extractionOf(id);
    const result = extractionResult(id);
    if (x.job.submittedAt) throw new Refusal(409, 'extraction_submitted', 'the tree was already proposed');
    const chosen = selection(body?.indexes, result.notes);
    const outs = proposeStored(result.drafts, chosen, x.job.companyId, (i) => ({
      origin: 'document',
      originDetail: detailOf(x.imp, result.notes[i].sentenceIndex),
    }));
    x.job.submittedAt = iso();
    return outs;
  }

  function cancelExtraction(id: string): T.DocumentExtraction {
    const job = extractionOf(id).job;
    if (job.state === 'queued' || job.state === 'running') {
      Object.assign(job, { state: 'cancelled', phase: null, cancelRequested: true, finishedAt: iso() });
      emit('extraction.changed', { extraction: { ...job } });
    }
    return { ...job };
  }

  /** Maps and stores an uploaded ontology or hierarchy file, as `POST /ontology-imports` does. */
  async function importOntology(
    file: { name: string; type: string; bytes: Uint8Array },
    fields: Record<string, string>,
  ): Promise<MockResponse> {
    try {
      if (!settings.importDocs) throw new Refusal(409, 'channel_disabled', 'document import is disabled in the admin portal');
      const company = companyOf(fields.companyId || '');
      if (!company) throw new Refusal(404, 'not_found', 'company not found');
      const root = concepts.find((c) => c.companyId === company.id && c.kind === 'root');
      const parent = fields.parentConceptId ? conceptById(fields.parentConceptId) : root;
      if (!parent || parent.companyId !== company.id || parent.dyingAt) throw new Refusal(404, 'not_found', 'parent concept not found');
      if (parent.pending) throw new Refusal(409, 'concept_pending', `${parent.label} is waiting for approval`);
      const languages = (fields.languages || 'en')
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);
      const format = fields.format ? (fields.format as T.OntologyFormat) : undefined;
      if (format && !ONTOLOGY_FORMATS.includes(format)) throw new Refusal(422, 'validation_failed', `format is one of ${ONTOLOGY_FORMATS.join(', ')}`);
      const mapped = mapOntologyFile(
        file.name,
        file.bytes,
        {
          companyId: company.id,
          parentId: parent.id,
          parentDomainKey: parent.kind === 'root' ? null : parent.domainKey,
          domainKeys: new Set(domains.map((t) => t.key)),
          domainKey: (fields.domainKey as T.DomainKey) || null,
          languages,
        },
        concepts
          .filter((c) => c.companyId === company.id && !c.dyingAt)
          .map((c) => ({ id: c.id, label: c.label, parentId: c.parentId, domainKey: c.domainKey })),
        format,
      );
      const expiresAt = nowDate().getTime() + ONTOLOGY_IMPORT_LIFETIME_MS;
      const result: T.OntologyImportResult = {
        ontologyImportId: uuid(),
        expiresAt: new Date(expiresAt).toISOString(),
        companyId: company.id,
        parentConceptId: fields.parentConceptId || null,
        format: mapped.format,
        languages,
        individuals: fields.individuals === 'as_concepts' ? 'as_concepts' : 'skip',
        drafts: mapped.drafts,
        notes: mapped.notes,
        skipped: mapped.skipped,
      };
      ontologyImports.set(result.ontologyImportId, { result, fileName: mapped.fileName, expiresAt, submitted: false });
      return json(200, result);
    } catch (e) {
      if (e instanceof Refusal) return problem(e);
      if (e instanceof ExtractRefusal) return problem(new Refusal(e.status, e.code, e.detail));
      throw e;
    }
  }

  /** The stored ontology import: 404 when unknown, 410 past its expiry. */
  function ontologyImportOf(id: string): MOntologyImport {
    const found = ontologyImports.get(id);
    if (!found) throw new Refusal(404, 'not_found', 'ontology import not found');
    if (nowDate().getTime() >= found.expiresAt) throw new Refusal(410, 'ontology_import_expired', 'the ontology import has expired; import it again');
    return found;
  }

  /** Creates the selected stored drafts in draft order with origin `ontology_import`, once. */
  function proposeOntologyImport(id: string, indexes: number[]): T.Proposal[] {
    const imp = ontologyImportOf(id);
    if (imp.submitted) throw new Refusal(409, 'ontology_import_submitted', 'the ontology import was proposed already');
    const { drafts, notes } = imp.result;
    const chosen = new Set(indexes);
    if (!indexes.length || chosen.size !== indexes.length || indexes.some((i) => !Number.isInteger(i) || i < 0 || i >= drafts.length))
      throw new Refusal(422, 'validation_failed', 'indexes must name distinct drafts');
    for (const i of indexes)
      if (notes[i].requires.some((r) => !chosen.has(r)))
        throw new Refusal(422, 'validation_failed', `draft ${i} requires a draft that is not selected`);
    const outs: T.Proposal[] = [];
    try {
      for (const i of [...chosen].sort((a, b) => a - b)) {
        provenance = { origin: 'ontology_import', originDetail: null, why: `Imported from ${imp.fileName} · ${notes[i].source.slice(0, 200)}` };
        const out = toProposal(createFromDraft(drafts[i], []));
        emit('proposal.created', { proposal: out, artefacts: out.artefacts, cascaded: [] });
        outs.push(out);
      }
    } finally {
      provenance = { origin: 'text', originDetail: null };
    }
    imp.submitted = true;
    return outs;
  }

  // ------------------------------------------------------------ routing

  const json = (status: number, body: unknown): MockResponse => ({ status, body });
  const problem = (r: Refusal): MockResponse =>
    json(r.status, { type: 'about:blank', title: r.code, status: r.status, detail: r.detail, code: r.code } satisfies T.Problem);

  /** A source's state and the freshness of what it feeds, for the canvas. */
  function emitSource(src: MSource): void {
    emit('source.changed', { source: toSource(src), bindings: bindings.filter((b) => b.sourceId === src.id).map(toBinding) });
  }

  function proposeChange(draft: T.ChangeDraft): MockResponse {
    const p = pChange(draft);
    const out = toProposal(p);
    emit('proposal.created', { proposal: out, artefacts: out.artefacts, cascaded: [] });
    return json(202, out);
  }

  const AUTHS: T.SourceAuth[] = ['service_principal', 'oauth2_client_credentials', 'managed_identity', 'key_vault_api_key'];
  const REFRESH: T.RefreshInterval[] = ['5 min', '15 min', '1 h', 'daily'];

  /** The administration routes: sources, connectors, directory, agents, cost, audit, appearance reset, cross-company. */
  function adminRoute(method: string, seg: string[], search: string, body: unknown): MockResponse | null {
    const is = (m: string, ...parts: (string | null)[]) =>
      method === m && seg.length === parts.length && parts.every((p, i) => p === null || p === seg[i]);
    const sourceOf = (id: string) => {
      const src = sourceById(id);
      if (!src || src.dyingAt) throw new Refusal(404, 'source_not_found', 'source does not exist');
      return src;
    };

    if (is('GET', 'connectors')) return json(200, CATALOG.map(([code, name, category, scopeText]) => ({ code, name, category, scopeText })));
    if (is('POST', 'connectors', null, 'discover')) {
      const code = decodeURIComponent(seg[1]);
      const req = (body || {}) as T.DiscoveryRequest;
      if (!AUTHS.includes(req.auth)) throw new Refusal(422, 'validation_failed', 'auth is required');
      if ((req.host || '').length > 300 || (req.scope || '').length > 500) throw new Refusal(422, 'validation_failed', 'host or scope is too long');
      const names = DISCOVER[code] || ['schema discovered'];
      const objects = names.map((name) => ({ name, rows: 200 + Math.floor(random() * 90000) }));
      return json(200, { connected: true, statusText: `Connected · read-only · ${names.length} objects discovered`, objects } satisfies T.Discovery);
    }
    if (is('GET', 'sources')) return json(200, sources.filter((n) => !n.dyingAt).map(toSource));
    if (is('POST', 'sources', 'refresh-all')) {
      let touched = 0;
      for (const c of concepts) {
        if (!c.bound) continue;
        const src = sourceById(c.bound.sourceId);
        if (src && !src.disabled) {
          c.bound.fresh = 'just now';
          touched++;
        }
      }
      addAudit('source', 'all sources refreshed', true);
      const live = sources.filter((n) => !n.dyingAt);
      for (const src of live) emitSource(src);
      return json(200, { sources: live.filter((n) => !n.disabled && !n.pending).length, bindings: touched } satisfies T.RefreshAllResult);
    }
    if (is('POST', 'sources')) {
      const p = createFromDraft({ ...(body as T.SourceDraft), type: 'source' }, []);
      const out = toProposal(p);
      emit('proposal.created', { proposal: out, artefacts: out.artefacts, cascaded: [] });
      return json(202, out);
    }
    if (is('GET', 'sources', null)) return json(200, toSource(sourceOf(seg[1])));
    if (is('PATCH', 'sources', null)) {
      const src = sourceOf(seg[1]);
      const patch = (body || {}) as T.SourceUpdate;
      if (patch.auth !== undefined && !AUTHS.includes(patch.auth)) throw new Refusal(422, 'validation_failed', 'unknown authentication method');
      if (patch.refresh !== undefined && !REFRESH.includes(patch.refresh)) throw new Refusal(422, 'validation_failed', 'unknown refresh interval');
      if ((patch.host || '').length > 300 || (patch.scope || '').length > 500) throw new Refusal(422, 'validation_failed', 'host or scope is too long');
      if (patch.host !== undefined) src.host = patch.host;
      if (patch.scope !== undefined) src.scope = patch.scope;
      if (patch.auth !== undefined) src.auth = patch.auth;
      if (patch.refresh !== undefined) src.refresh = patch.refresh;
      addAudit('source', `${src.label} reconfigured`, true);
      emitSource(src);
      return json(200, toSource(src));
    }
    if (is('POST', 'sources', null, 'enable') || is('POST', 'sources', null, 'disable')) {
      const src = sourceOf(seg[1]);
      if (src.pending) throw new Refusal(409, 'source_pending', 'the source is awaiting approval');
      const off = seg[2] === 'disable';
      if (src.disabled !== off) {
        src.disabled = off;
        for (const b of bindings) if (b.sourceId === src.id && conceptById(b.conceptId)?.bound === b) b.fresh = off ? 'paused' : '2 min';
        addAudit('source', `${src.label} ${off ? 'disabled' : 'enabled'}`, true);
      }
      emitSource(src);
      return json(200, toSource(src));
    }
    if (is('DELETE', 'sources', null)) return proposeChange({ type: 'change', changeKind: 'remove_source', payload: { sourceId: seg[1] } });
    if (is('DELETE', 'bindings', null)) return proposeChange({ type: 'change', changeKind: 'unbind', payload: { bindingId: seg[1] } });
    if (is('DELETE', 'companies', null)) return proposeChange({ type: 'change', changeKind: 'remove_company', payload: { companyId: seg[1] } });
    if (is('GET', 'domains')) return json(200, [...domains].sort((a, b) => a.position - b.position).map(toTenantDomain));
    if (is('POST', 'domains')) {
      const input = (body || {}) as T.DomainInput;
      return proposeChange({ type: 'change', changeKind: 'create_domain', payload: { name: input.name, color: input.color, owner: input.owner } });
    }
    if (is('PATCH', 'domains', null)) {
      const key = decodeURIComponent(seg[1]);
      if (!DOMAIN_KEY.test(key)) throw new Refusal(422, 'validation_failed', 'domainKey does not match the key pattern');
      const patch = (body || {}) as T.DomainPatch;
      return proposeChange({ type: 'change', changeKind: 'edit_domain', payload: { domainKey: key, name: patch.name, color: patch.color, owner: patch.owner } });
    }
    if (is('DELETE', 'domain-products', null)) return proposeChange({ type: 'change', changeKind: 'delete_domain', payload: { domainProductId: seg[1] } });
    if (is('POST', 'concepts', null, 'move')) {
      const key = (body as { domainKey?: unknown } | undefined)?.domainKey;
      if (typeof key !== 'string' || !DOMAIN_KEY.test(key)) throw new Refusal(422, 'validation_failed', 'domainKey is required');
      return proposeChange({ type: 'change', changeKind: 'move_concept_domain', payload: { conceptId: seg[1], domainKey: key } });
    }
    if (is('POST', 'deletion-impact')) return json(200, deletionImpact(body as T.DeletionTarget));
    if (is('POST', 'proposals', 'bulk-delete')) {
      const req = (body || {}) as T.BulkDeleteRequest;
      return proposeChange({
        type: 'change',
        changeKind: 'delete_bulk',
        payload: { companyId: req.companyId, conceptIds: req.conceptIds, domainProductIds: req.domainProductIds },
      });
    }
    if (is('POST', 'settings', 'cross-company', 'disable')) {
      if ((body as { confirmation?: string } | undefined)?.confirmation !== 'disable')
        throw new Refusal(409, 'confirmation_mismatch', 'type disable to confirm');
      const cross = relations.filter((l) => !l.dyingAt && conceptById(l.aId)?.companyId !== conceptById(l.bId)?.companyId);
      const t = iso();
      for (const l of cross) l.dyingAt = t;
      emit('relation.removed', { relationIds: cross.map((l) => l.id) });
      let rejected = 0;
      for (const q of open()) {
        const l = relationById(q.relationId);
        if (q.type === 'relation' && l && cross.includes(l)) {
          reject(q, []);
          rejected++;
        }
      }
      settings.crossCompany = false;
      const n = cross.length;
      const entry = addAudit('setting', `companies may interact disabled · ${n} cross-company relationship${n === 1 ? '' : 's'} removed`, true);
      const bulk = newProposal({
        type: 'change',
        changeKind: 'remove_relation',
        title: `Remove ${n} cross-company relationship${n === 1 ? '' : 's'}`,
        heading: KIND_HEADING.change,
        color: C.conflict,
        companyId: null,
        domainId: null,
        parentLabel: null,
        deps: [],
        ready: () => true,
        waitFor: null,
        html: `Remove ${n} cross-company relationship${n === 1 ? '' : 's'}`,
        why: 'confirmed by typing disable',
        caption: null,
        conceptId: null,
        relationId: null,
        relationIds: [],
        sourceId: null,
        bindingIds: [],
        attributeId: null,
      });
      bulk.state = 'approved';
      bulk.decidedAt = t;
      relations = relations.filter((l) => !l.dyingAt);
      emit('settings.changed', { settings: { ...settings } });
      return json(200, {
        removedRelations: n,
        rejectedProposals: rejected,
        proposal: toProposal(bulk),
        audit: entry,
        settings: { ...settings },
      } satisfies T.CrossCompanyDisabled);
    }
    if (is('POST', 'appearance', 'reset')) {
      appearance.colors = {};
      appearance.accent = '#3fb8a9';
      appearance.source = DEFAULT_BRASS;
      addAudit('setting', 'colours reset', true);
      emit('appearance.changed', { appearance: toAppearance() });
      return json(200, toAppearance());
    }
    if (is('GET', 'audit'))
      return json(
        200,
        pageOf(audit, parseListArgs(search), {
          search: (x) => [x.kind, x.what],
          filters: { kind: (x) => x.kind, ok: (x) => String(x.ok), actorKind: (x) => x.actor.kind },
          sorts: {},
        }),
      );
    if (is('GET', 'users')) return json(200, directory.listUsers(search));
    if (is('GET', 'users', null)) return json(200, directory.getUser(seg[1]));
    if (is('GET', 'groups')) return json(200, directory.listGroups(search));
    if (is('POST', 'groups')) return json(201, directory.createGroup(body as T.GroupInput));
    if (is('GET', 'groups', null)) return json(200, directory.getGroup(seg[1]));
    if (is('PATCH', 'groups', null)) return json(200, directory.updateGroup(seg[1], body as T.GroupInput));
    if (is('DELETE', 'groups', null)) {
      directory.deleteGroup(seg[1]);
      return json(204, undefined);
    }
    if (is('PUT', 'groups', null, 'members', null) || is('DELETE', 'groups', null, 'members', null)) {
      directory.setMember(seg[1], seg[3], method === 'PUT');
      return json(204, undefined);
    }
    if (is('POST', 'groups', null, 'roles')) return json(201, directory.addRole(seg[1], body as { role: T.RoleName; scope: T.Scope }));
    if (is('DELETE', 'groups', null, 'roles', null)) {
      directory.removeRole(seg[1], seg[3]);
      return json(204, undefined);
    }
    if (is('GET', 'roles')) return json(200, directory.listRoles());
    if (is('GET', 'roles', null, 'groups')) return json(200, directory.listRoleGroups(seg[1]));
    if (is('GET', 'scopes')) return json(200, directory.listScopes());
    if (is('GET', 'agents')) return json(200, directory.listAgents(search));
    if (is('PATCH', 'agents', null)) return json(200, directory.updateAgent(seg[1], body as { access?: unknown }));
    if (is('GET', 'cost'))
      return json(200, {
        ...directory.cost(`${iso().slice(0, 7)}-01`),
        llm: { calls: 0, inputTokens: 0, outputTokens: 0, tokensUsed: 0, tokenCap: settings.llmMonthlyTokenCap, ocrPagesUsed: 0, ocrPageCap: settings.ocrMonthlyPageCap, costEur: 0, byPurpose: [] },
      });
    return null;
  }

  function route(method: string, rawPath: string, body: unknown): MockResponse {
    const [path] = rawPath.split('?');
    const search = rawPath.includes('?') ? rawPath.slice(rawPath.indexOf('?')) : '';
    const seg = path.replace(/^\/+|\/+$/g, '').split('/');
    const is = (m: string, ...parts: (string | null)[]) =>
      method === m && seg.length === parts.length && parts.every((p, i) => p === null || p === seg[i]);

    const admin = adminRoute(method, seg, search, body);
    if (admin) return admin;
    if (is('GET', 'scene')) return json(200, toScene());
    if (is('GET', 'proposals')) {
      const items = open().map(toProposal);
      return json(200, { items, page: 1, pageSize: items.length || 1, total: items.length });
    }
    if (is('POST', 'proposals')) return json(202, createDrafts([body as T.ProposalDraft])[0]);
    if (is('POST', 'proposals', 'batch')) {
      const batch = body as { drafts: T.ProposalDraft[]; origin?: T.InputOrigin; importRef?: T.ImportRef };
      return json(202, createDrafts(batch.drafts || [], { origin: batch.origin, importRef: batch.importRef }));
    }
    if (is('POST', 'proposals', 'approve-all')) return json(200, approveAll());
    if (is('POST', 'proposals', null, 'approve-branch')) {
      const p = proposals.find((x) => x.id === seg[1]);
      if (!p) throw new Refusal(404, 'proposal_not_found', 'proposal does not exist');
      return json(200, approveBranch(p));
    }
    if (is('POST', 'concepts', null, 'expand')) return json(200, expand(seg[1], (body || {}) as T.ExpansionRequest));
    if (is('POST', 'expansions', null, 'proposals')) return json(202, proposeExpansion(seg[1], (body || {}) as { indexes?: unknown }));
    if (is('POST', 'import', null, 'extraction')) return json(202, startExtraction(seg[1], (body || {}) as { companyId?: string }));
    if (is('GET', 'extractions', null)) return json(200, readExtraction(seg[1]));
    if (is('DELETE', 'extractions', null)) return json(202, cancelExtraction(seg[1]));
    if (is('GET', 'extractions', null, 'result')) return json(200, extractionResult(seg[1]));
    if (is('POST', 'extractions', null, 'proposals')) return json(202, proposeExtraction(seg[1], (body || {}) as { indexes?: unknown }));
    if (is('POST', 'proposals', 'reject-all')) {
      let rejected = 0;
      for (const p of open()) {
        if (p.state !== 'pending' && p.state !== 'half_approved') continue;
        reject(p, []);
        rejected++;
      }
      return json(200, { approved: 0, rejected, rounds: 1, remaining: open().length, caption: 'All pending proposals were discarded.' } satisfies T.BulkResult);
    }
    if (is('GET', 'proposals', null)) {
      const p = proposals.find((x) => x.id === seg[1]);
      if (!p) throw new Refusal(404, 'proposal_not_found', 'proposal does not exist');
      return json(200, toProposal(p));
    }
    if (is('PATCH', 'proposals', null)) {
      const p = proposals.find((x) => x.id === seg[1]);
      if (!p) throw new Refusal(404, 'proposal_not_found', 'proposal does not exist');
      return json(200, editProposal(p, body as T.ProposalEdit));
    }
    if (is('POST', 'proposals', null, 'approve') || is('POST', 'proposals', null, 'second-approve')) {
      const p = proposals.find((x) => x.id === seg[1]);
      if (!p) throw new Refusal(404, 'proposal_not_found', 'proposal does not exist');
      if (p.state !== 'pending' && p.state !== 'half_approved') throw new Refusal(409, 'proposal_decided', 'already decided');
      if (seg[2] === 'second-approve' && p.state !== 'half_approved')
        throw new Refusal(409, 'proposal_not_half_approved', 'the proposal is not half approved');
      const raw = new URLSearchParams(search).get('expectedRevision');
      let expected: number | undefined;
      if (raw !== null) {
        expected = Number(raw);
        if (!Number.isInteger(expected) || expected < 0) throw new Refusal(422, 'validation_failed', 'expectedRevision is a whole number');
      }
      return json(200, approve(p, false, [], expected));
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
      for (const k of Object.keys(patch))
        if (k === 'approvalRequired' || k === 'readOnlyConnectors') throw new Refusal(409, 'locked_setting', `${k} is always on`);
      if (
        patch.crossCompany === false &&
        settings.crossCompany &&
        relations.some((l) => !l.dyingAt && conceptById(l.aId)?.companyId !== conceptById(l.bId)?.companyId)
      )
        throw new Refusal(409, 'confirmation_required', 'companies already interact; confirm by typing disable');
      for (const k of Object.keys(patch) as (keyof T.SettingsPatch)[]) {
        if (k === 'refresh') {
          settings.refresh = patch.refresh as T.RefreshInterval;
          addAudit('setting', `refresh interval ${patch.refresh}`, true);
          continue;
        }
        if (k === 'llmMonthlyTokenCap') {
          const cap = patch.llmMonthlyTokenCap;
          if (typeof cap !== 'number' || !Number.isInteger(cap) || cap < 0 || cap > 1_000_000_000)
            throw new Refusal(422, 'validation_failed', 'llmMonthlyTokenCap is a whole number from 0 to 1,000,000,000');
          settings.llmMonthlyTokenCap = cap;
          addAudit('setting', `llmMonthlyTokenCap set to ${cap}`, true);
          continue;
        }
        if (k === 'ocrMonthlyPageCap') {
          const cap = patch.ocrMonthlyPageCap;
          if (typeof cap !== 'number' || !Number.isInteger(cap) || cap < 0 || cap > 1_000_000)
            throw new Refusal(422, 'validation_failed', 'ocrMonthlyPageCap is a whole number from 0 to 1,000,000');
          settings.ocrMonthlyPageCap = cap;
          addAudit('setting', `ocrMonthlyPageCap set to ${cap}`, true);
          continue;
        }
        if (typeof patch[k] === 'boolean') (settings as unknown as Record<string, boolean>)[k] = patch[k] as boolean;
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
      return json(200, { coverage } satisfies T.ViewState);
    }
    if (is('POST', 'teach', 'parse')) return json(200, teachParse(body as T.TeachRequest));
    if (is('POST', 'teach', 'parse', 'stream')) return { status: 200, body: null, lines: streamedParse(teachParse(body as T.TeachRequest)) };
    if (is('POST', 'ontology-imports'))
      throw new Refusal(422, 'validation_failed', 'the file is sent as multipart form data in the field file');
    if (is('GET', 'ontology-imports', null)) return json(200, ontologyImportOf(seg[1]).result);
    if (is('POST', 'ontology-imports', null, 'proposals'))
      return json(202, proposeOntologyImport(seg[1], ((body || {}) as { indexes?: number[] }).indexes || []));
    // No Speech resource behind the mock: the microphone uses the browser's recogniser.
    if (is('POST', 'speech', 'token')) throw new Refusal(503, 'unavailable', 'speech recognition is not configured');
    // The export files are written by the Ontaix API; the mock has no writer for them.
    if (is('GET', 'export')) throw new Refusal(503, 'unavailable', 'export needs the Ontaix API');
    if (is('POST', 'import', 'sentences'))
      throw new Refusal(422, 'validation_failed', 'the document is sent as multipart form data in the field file');
    if (is('GET', 'healthz')) return json(200, { status: 'ok' });
    throw new Refusal(404, 'not_found', `${method} ${path} is not part of the mock API`);
  }

  return {
    importDocument,
    detectImport,
    importOntology,
    handle(method, path, body) {
      try {
        return route(method.toUpperCase(), path, body);
      } catch (e) {
        if (e instanceof Refusal) return problem(e);
        if (e instanceof DirectoryRefusal) return problem(new Refusal(e.status, e.code, e.detail));
        throw e;
      }
    },
  };
}
