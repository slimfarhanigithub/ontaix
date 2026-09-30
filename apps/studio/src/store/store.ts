/**
 * The Studio store: one scene state the verbatim canvas modules run on, the shell state React
 * renders, and the actions that call the API. Every ontology change reaches the canvas through
 * a live event (proposal created, approved, rejected, conflict noticed), never from the HTTP
 * response, so the same path serves the in-browser mock and a WebSocket-fed API.
 */
import { api } from '../api/client';
import { liveEvents, type ConceptConflictPayload, type Envelope, type ProposalEventPayload } from '../api/events';
import {
  ApiError,
  isBinding,
  isSource,
  type Appearance,
  type Artefacts,
  type Attribute,
  type Binding,
  type ConnectorType,
  type Company as ApiCompany,
  type DomainProduct,
  type Proposal,
  type ProposalDraft,
  type Scene,
  type Settings,
  type Source,
} from '../api/types';
import { arrange as arrangeCanvas } from '../canvas/arrange';
import { GREEN, RED, DEFAULT_BRASS, DEFAULT_COLORS, DOMAIN_TEMPLATES } from '../canvas/constants';
import { divide, type BirthDraws } from '../canvas/division';
import { focusOnCell, focusOnDomain } from '../canvas/focus';
import { hideLineageState, showLineageState } from '../canvas/lineage';
import type { Renderer } from '../canvas/renderer';
import {
  addCompany,
  addLink,
  addNode,
  addSource,
  bySid,
  createScene,
  domainOf,
  layoutCompanies,
  linkBySid,
  type SceneState,
} from '../canvas/state';
import type { Attr, Company, Domain, Link, Node } from '../canvas/types';
import { random } from '../runtime/rng';
import { now } from '../runtime/clock';
import type { CustomDialog, DialogEntry, DialogSpec } from '../shell/Dialog';
import { readSkipAnimation, writeSkipAnimation } from './skipAnimation';

/** An attribute as the canvas holds it: a taught one keeps its value and has no column or fill. */
function toAttr(a: Attribute, state: Attr['state'] = a.state): Attr {
  return { sid: a.id, name: a.name, type: a.type, col: a.col ?? '', fill: a.fill ?? 0, value: a.value ?? undefined, state };
}

/** 409 codes that mean the proposal changed under the caller, so the scene is reloaded. */
const STALE_PROPOSAL_CODES = new Set(['proposal_decided', 'proposal_not_ready']);

/** A toast: a strong lead word and plain text, both rendered as text nodes. */
export interface Toast {
  id: number;
  strong: string;
  text: string;
}

/** One entry of the teach bar history: a caption, or a refusal toast copied there to be re-read. */
export interface CaptionEntry {
  seq: number;
  kicker: string;
  text: string;
  /** A refusal or a sentence the model did not understand; its kicker shows in the conflict colour. */
  refused: boolean;
}

/** Captions the teach bar history keeps, newest last. */
export const HISTORY_SIZE = 5;

export interface NewBoxState {
  host: Node;
  left: number;
  top: number;
}

export interface LinkBoxState {
  a: Node;
  b: Node;
  link: Link | null;
  reverse: boolean;
  left: number;
  top: number;
}

export interface UiState {
  status: 'loading' | 'ready' | 'error';
  proposals: Proposal[];
  caption: { kicker: string; text: string; seq: number };
  /** The last captions and refusals, oldest first, at most HISTORY_SIZE; identical neighbours merge. */
  history: CaptionEntry[];
  say: string;
  sayPlaceholder: string;
  panelOff: boolean;
  legendOff: boolean;
  domainsOff: boolean;
  adminOpen: boolean;
  theme: 'dark' | 'light';
  settings: Settings | null;
  appearance: Appearance | null;
  drawerNode: Node | null;
  drawerSeq: number;
  lineageOn: boolean;
  newBox: NewBoxState | null;
  linkBox: LinkBoxState | null;
  toasts: Toast[];
  importing: boolean;
  /** Teach bar parses in flight: typed sentences, queued spoken sentences and document imports. */
  processing: number;
  /** The cell whose Expand suggestions are loading. */
  expanding: Node | null;
  listening: boolean;
  /** The user's Skip animation choice (Admin portal, Appearance, or S); the tenant's Animations off skips too. */
  skipAnimation: boolean;
  /** Open dialogs, bottom first. */
  dialogs: DialogEntry[];
  /** Page the admin portal shows; kept while the portal is closed. */
  adminPage: string;
  /** Bumped whenever the portal re-renders from scratch, which resets its lists. */
  adminRev: number;
  connectors: ConnectorType[];
}

type Listener = () => void;

/** Calls one Approve branch click makes at most while the API reports the branch incomplete. */
const MAX_BRANCH_CALLS = 100;


class StudioStore {
  readonly s: SceneState;
  readonly ui: UiState;
  renderer: Renderer | null = null;
  private version = 0;
  private listeners = new Set<Listener>();
  private toastSeq = 0;
  private dialogSeq = 0;
  private historySeq = 0;
  private refreshQueued = false;
  private unsubscribeEvents: (() => void) | null = null;
  private loading: Promise<void> | null = null;
  /** Birth draws made when a draft was posted, keyed by company id and label, used when the proposal event arrives. */
  private births = new Map<string, BirthDraws>();

  constructor() {
    this.s = createScene({
      caption: (k, t) => this.caption(k, t),
      arrangeTitle: () => this.bump(),
      domainsChanged: () => this.bump(),
      companiesChanged: () => this.renderCompanies(),
    });
    this.ui = {
      status: 'loading',
      proposals: [],
      caption: { kicker: '', text: '', seq: 0 },
      history: [],
      say: '',
      sayPlaceholder: '',
      panelOff: false,
      legendOff: false,
      domainsOff: false,
      adminOpen: false,
      theme: 'dark',
      settings: null,
      appearance: null,
      drawerNode: null,
      drawerSeq: 0,
      lineageOn: false,
      newBox: null,
      linkBox: null,
      toasts: [],
      importing: false,
      processing: 0,
      expanding: null,
      listening: false,
      skipAnimation: readSkipAnimation(),
      dialogs: [],
      adminPage: 'sources',
      adminRev: 0,
      connectors: [],
    };
    this.syncSkip();
  }

  // ------------------------------------------------------------ subscription

  subscribe = (fn: Listener): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  getVersion = (): number => this.version;

  bump(): void {
    this.version++;
    for (const fn of this.listeners) fn();
  }

  // ------------------------------------------------------------ lifecycle

  attachRenderer(r: Renderer): void {
    this.renderer = r;
    r.applyTheme(this.ui.theme);
  }

  /** Loads the scene and starts listening to live events; a second call joins the first. The
   * caption stays empty until the first teach, import or decision. */
  load(): Promise<void> {
    if (!this.loading) this.loading = this.loadOnce();
    return this.loading;
  }

  private async loadOnce(): Promise<void> {
    if (!this.unsubscribeEvents) this.unsubscribeEvents = liveEvents.subscribe((e) => this.handleEvent(e));
    try {
      const scene = await api.getScene();
      this.applyScene(scene);
      this.ui.status = 'ready';
    } catch (err) {
      console.error('scene load failed', err);
      this.ui.status = 'error';
    }
    document.documentElement.dataset.ontaixReady = this.ui.status;
    this.bump();
  }

  /** Fills the canvas arrays from a snapshot, the way the reference's `restore` does. */
  applyScene(scene: Scene): void {
    const s = this.s;
    s.nodes.length = 0;
    s.links.length = 0;
    s.companies.length = 0;
    s.DOMAINS = [];
    s.activeCompany = null;
    s.BRASS = scene.appearance.source || DEFAULT_BRASS;
    for (const t of DOMAIN_TEMPLATES) t.color = scene.appearance.colors[t.key] || DEFAULT_COLORS[t.key];
    for (const co of [...scene.companies].sort((a, b) => a.position - b.position)) {
      const c = addCompany(s, co.name, co.sub);
      this.bindCompany(c, co);
    }
    for (const n of scene.nodes) {
      if (isSource(n)) {
        const c = this.companyBySid(n.companyId);
        if (!c) continue;
        const src = addSource(s, c, n.label, n.kindText);
        src.sid = n.id;
        src.ai = n.anchorIndex;
        src.pending = n.pending;
        src.disabled = n.disabled;
        src.alpha = 1;
        continue;
      }
      if (n.kind === 'root') {
        const c = this.companyBySid(n.companyId);
        if (c?.root) c.root.sid = n.id;
        continue;
      }
      const c = this.companyBySid(n.companyId);
      if (!c) continue;
      const node = addNode(s, {
        sid: n.id,
        label: n.label,
        sub: n.sub || '',
        kind: 'concept',
        color: n.color || DEFAULT_BRASS,
        finalColor: n.color || null,
        company: c,
        domain: n.domainKey ? domainOf(s, n.domainKey, c) : null,
        x: n.x,
        y: n.y,
        pending: !!n.pending,
        conflict: !!n.conflict,
        pinned: !!n.pinned,
      });
      node._rule = n.rule || undefined;
      node.attrs = n.attributes.map((a) => toAttr(a));
      node.alpha = 1;
      node.labelAlpha = 1;
    }
    for (const l of scene.links) {
      if (isBinding(l)) {
        const a = bySid(s, l.sourceId),
          b = bySid(s, l.conceptId);
        if (!a || !b) continue;
        const link = addLink(s, a, b, 'bind', 300, 'bound to');
        link.sid = l.id;
        link.pending = l.pending;
        link.alpha = 1;
        if (!l.pending) b.bound = { source: a, records: l.records, fresh: l.fresh };
        continue;
      }
      const a = bySid(s, l.aId),
        b = bySid(s, l.bId);
      if (!a || !b) continue;
      const link = addLink(s, a, b, l.kind, l.rest, l.label, l.seed);
      link.sid = l.id;
      link.pending = l.pending;
      link.alpha = 1;
    }
    for (const n of scene.nodes) {
      if (isSource(n) || n.kind === 'root') continue;
      const node = bySid(s, n.id);
      if (!node) continue;
      if (n.parentId) {
        const parent = bySid(s, n.parentId);
        if (parent) {
          node.parent = parent;
          node.birthLink = linkBySid(s, n.birthRelationId) || null;
        }
      }
      node.bornAt = new Date(n.bornAt);
    }
    layoutCompanies(s);
    s.activeCompany = s.companies[0] || null;
    this.ui.proposals = scene.proposals;
    this.ui.settings = scene.settings;
    this.ui.appearance = scene.appearance;
    this.ui.connectors = scene.connectors || [];
    this.setTheme(scene.appearance.theme, false);
    this.applyColors();
    this.applySettings();
    if (scene.viewState.coverage !== s.COVERAGE) s.COVERAGE = scene.viewState.coverage;
    s.userZoomed = false;
    this.renderCompanies();
    this.bump();
  }

  private bindCompany(c: Company, co: ApiCompany): void {
    c.sid = co.id;
    if (c.root) c.root.sid = co.rootId;
    for (const dp of co.domainProducts) {
      const d = c.domains.find((x) => x.key === dp.key);
      if (d) this.bindDomain(d, dp);
    }
  }

  private bindDomain(d: Domain, dp: DomainProduct): void {
    d.sid = dp.id;
    d.version = Math.round((1 + dp.revision * 0.1) * 10) / 10;
    d.hidden = dp.hidden;
    d.color = dp.color;
  }

  companyBySid(sid: string | null | undefined): Company | null {
    return sid ? this.s.companies.find((c) => c.sid === sid) || null : null;
  }

  domainBySid(sid: string | null | undefined): Domain | null {
    return sid ? this.s.DOMAINS.find((d) => d.sid === sid) || null : null;
  }

  // ------------------------------------------------------------ events

  handleEvent(e: Envelope): void {
    switch (e.type) {
      case 'proposal.created':
        this.applyCreated((e.payload as unknown as ProposalEventPayload).proposal);
        this.queueRefresh();
        break;
      case 'proposal.approved':
        this.applyApproved(e.payload as unknown as ProposalEventPayload, e.bulk);
        this.queueRefresh();
        break;
      case 'proposal.half_approved':
        this.queueRefresh();
        break;
      case 'proposal.rejected':
        this.applyRejected(e.payload as unknown as ProposalEventPayload);
        this.queueRefresh();
        break;
      case 'concept.conflict': {
        const p = e.payload as unknown as ConceptConflictPayload;
        const a = bySid(this.s, p.concepts[0]?.id),
          b = bySid(this.s, p.concepts[1]?.id);
        if (a && b) {
          a.conflict = b.conflict = true;
          const l = addLink(this.s, a, b, 'clash', p.relation.rest, p.relation.label);
          l.sid = p.relation.id;
          this.caption('The model noticed', p.caption);
        }
        break;
      }
      case 'company.created': {
        const co = e.payload.company as ApiCompany;
        if (this.companyBySid(co.id)) break;
        const c = addCompany(this.s, co.name, co.sub);
        this.bindCompany(c, co);
        this.bump();
        break;
      }
      case 'domain_product.changed': {
        const dp = e.payload.domainProduct as DomainProduct;
        const d = this.domainBySid(dp.id);
        if (d) this.bindDomain(d, dp);
        this.bump();
        break;
      }
      case 'settings.changed':
        this.ui.settings = e.payload.settings as Settings;
        this.applySettings();
        break;
      case 'appearance.changed':
        this.ui.appearance = e.payload.appearance as Appearance;
        this.applyColors();
        break;
      case 'source.changed':
        this.applySourceChanged(e.payload.source as Source, (e.payload.bindings as Binding[] | undefined) || []);
        break;
      case 'relation.removed':
        for (const id of (e.payload.relationIds as string[] | undefined) || []) this.fadeLink(linkBySid(this.s, id));
        this.bump();
        break;
      case 'snapshot.required':
        void this.reloadScene();
        break;
      default:
        break;
    }
  }

  /** Brings the whole canvas back to the server snapshot, keeping the camera. */
  async reloadScene(): Promise<void> {
    try {
      const scene = await api.getScene();
      this.applyScene(scene);
    } catch (err) {
      this.refused(err);
    }
  }

  /** Re-reads the open proposals once per burst of events, for their server-evaluated readiness. */
  private queueRefresh(): void {
    if (this.refreshQueued) return;
    this.refreshQueued = true;
    queueMicrotask(() => {
      this.refreshQueued = false;
      void this.refreshProposals();
    });
  }

  async refreshProposals(): Promise<void> {
    try {
      const page = await api.listProposals();
      this.ui.proposals = page.items;
    } catch (err) {
      console.error('proposal refresh failed', err);
    }
    this.bump();
  }

  /** Remembers the draws made for a draft so the birth reuses them when its event arrives. */
  rememberBirth(companyId: string, label: string, draws: BirthDraws): void {
    this.births.set(`${companyId}|${label.toLowerCase()}`, draws);
  }

  private takeBirth(companyId: string, label: string): BirthDraws | undefined {
    const k = `${companyId}|${label.toLowerCase()}`;
    const d = this.births.get(k);
    this.births.delete(k);
    return d;
  }

  /** A proposal's pending artefacts appear at once: a cell divides off its parent, a line grows lighter. */
  applyCreated(p: Proposal): void {
    const s = this.s;
    const art = p.artefacts || {};
    switch (p.type) {
      case 'concept':
      case 'spec': {
        const c = art.concepts?.[0],
          r = art.relations?.[0];
        if (!c || !r || bySid(s, c.id)) return;
        const parent = bySid(s, c.parentId);
        if (!parent) return;
        const isa = r.kind === 'isa';
        // The bend is the server's stored seed; the angle noise and node seed come from the
        // draws made when the draft was posted, or are drawn now for a proposal another client made.
        const own = this.takeBirth(c.companyId, c.label);
        const draws: BirthDraws = own ? { ...own, link: r.seed } : { noise: random(), node: random() * 100, link: r.seed };
        const n = divide(s, parent, c.label, null, {
          label: isa ? undefined : r.label,
          domain: c.domainKey ?? null,
          isa,
          reverse: !isa && r.aId === c.id,
          draws,
        });
        n.sid = c.id;
        n.pending = true;
        if (n.birthLink) {
          n.birthLink.sid = r.id;
          n.birthLink.pending = true;
        }
        if (p.type === 'spec') {
          const rule = c.rule || '';
          n._rule = rule;
          setTimeout(
            () => {
              n.sub = rule;
            },
            s.SKIP ? 0 : 900,
          );
        }
        break;
      }
      case 'relation': {
        const r = art.relations?.[0];
        if (!r || linkBySid(s, r.id)) return;
        const a = bySid(s, r.aId),
          b = bySid(s, r.bId);
        if (!a || !b) return;
        const l = addLink(s, a, b, r.kind, r.rest, r.label, r.seed);
        l.sid = r.id;
        l.pending = true;
        break;
      }
      case 'source': {
        const src = art.sources?.[0];
        if (!src || bySid(s, src.id)) return;
        const c = this.companyBySid(src.companyId);
        if (!c) return;
        const n = addSource(s, c, src.label, src.kindText);
        n.sid = src.id;
        n.pending = true;
        break;
      }
      case 'bind': {
        for (const b of art.bindings || []) {
          if (linkBySid(s, b.id)) continue;
          const src = bySid(s, b.sourceId),
            c = bySid(s, b.conceptId);
          if (!src || !c) continue;
          const l = addLink(s, src, c, 'bind', 300, 'bound to');
          l.sid = b.id;
          l.pending = true;
        }
        break;
      }
      case 'attr': {
        for (const a of art.attributes || []) {
          const n = bySid(s, a.conceptId);
          if (!n || n.attrs.some((x) => x.sid === a.id)) continue;
          n.attrs.push(toAttr(a, 'proposed'));
          if (this.ui.drawerNode === n) this.ui.drawerSeq++;
        }
        break;
      }
      case 'change':
        break;
    }
  }

  applyApproved(payload: ProposalEventPayload, bulk: boolean): void {
    const s = this.s;
    const p = payload.proposal;
    if (!bulk) this.toast2('Approved', p.title);
    const node = bySid(s, p.conceptId);
    if (node && p.type !== 'attr' && p.type !== 'change') {
      node.pending = false;
      node.flash = { color: GREEN, start: now(), soft: !!bulk };
    }
    const link = linkBySid(s, p.relationId);
    if (link && p.type !== 'change') link.pending = false;
    for (const id of p.relationIds) {
      const l = linkBySid(s, id);
      if (l) l.pending = false;
    }
    for (const b of payload.artefacts.bindings || []) {
      const l = linkBySid(s, b.id);
      if (l) {
        l.pending = false;
        l.grow = { start: now() };
      }
      const source = bySid(s, b.sourceId),
        target = bySid(s, b.conceptId);
      if (!b.pending && source && target) target.bound = { source, records: b.records, fresh: b.fresh };
    }
    const src = bySid(s, p.sourceId);
    if (src && p.type === 'source') {
      src.pending = false;
      src.flash = { color: GREEN, start: now(), soft: !!bulk };
    }
    if (p.changeKind === 'unbind' && node) {
      this.fadeLink(s.links.find((l) => l.kind === 'bind' && l.b === node && !l.pending));
      node.bound = null;
    }
    if (p.changeKind === 'remove_source' && src)
      for (const l of s.links)
        if (l.kind === 'bind' && l.a === src) {
          if (l.b.bound && l.b.bound.source === src) l.b.bound = null;
          this.fadeLink(l);
        }
    if (p.changeKind === 'remove_company') this.removeCompanyLater(this.companyBySid(p.companyId));
    if (p.changeKind === 'resolve_conflict') this.resolveConflictLinks(payload.artefacts);
    this.reconcile(payload.artefacts, p.changeKind === 'edit_relation');
    for (const q of payload.cascaded) {
      if (q.state === 'pending') this.applyCreated(q);
      else if (q.state === 'approved' && q.artefacts) this.reconcile(q.artefacts, false);
    }
    if (p.caption) this.caption('Approved', p.caption);
    this.bump();
  }

  applyRejected(payload: ProposalEventPayload): void {
    const s = this.s;
    const apply = (p: Proposal) => {
      const node = bySid(s, p.conceptId);
      if (node && (p.type === 'concept' || p.type === 'spec')) {
        node.dying = { start: now(), color: RED };
        node.pending = false;
      }
      const dropLink = (id: string | null | undefined) => {
        const l = linkBySid(s, id);
        if (!l) return;
        const j = s.links.indexOf(l);
        if (j >= 0) s.links.splice(j, 1);
      };
      if (p.type !== 'change') dropLink(p.relationId);
      for (const id of p.relationIds) dropLink(id);
      for (const id of p.bindingIds) dropLink(id);
      const src = bySid(s, p.sourceId);
      if (src && p.type === 'source') src.dying = { start: now(), color: RED };
      // A taught attribute's proposal names no concept; its attribute is found on its holder.
      const holder = p.type === 'attr' ? node || s.nodes.find((n) => n.attrs.some((a) => a.sid === p.attributeId)) : null;
      if (holder) {
        const i = holder.attrs.findIndex((a) => a.sid === p.attributeId);
        if (i >= 0) holder.attrs.splice(i, 1);
        if (this.ui.drawerNode === holder) this.ui.drawerSeq++;
      }
    };
    for (const q of payload.cascaded) apply(q);
    apply(payload.proposal);
    if (payload.caption) this.caption('Rejected', payload.caption);
    this.bump();
  }

  /** Brings local cells, lines and domains to the server state of the artefacts a decision touched. */
  private reconcile(art: Artefacts, regrow: boolean): void {
    const s = this.s;
    for (const c of art.concepts || []) {
      const n = bySid(s, c.id);
      if (!n) continue;
      n.label = c.label;
      if (c.sub) n.sub = c.sub;
      n.conflict = c.conflict;
      n.pending = c.pending;
      if (c.dyingAt && !n.dying) n.dying = { start: now(), color: RED };
      if (c.bound && !c.bound.pending) {
        const source = bySid(s, c.bound.sourceId);
        if (source) n.bound = { source, records: c.bound.records, fresh: c.bound.fresh };
      } else if (!c.bound) n.bound = null;
      n.attrs = c.attributes.map((a) => toAttr(a));
      if (this.ui.drawerNode === n) this.ui.drawerSeq++;
    }
    for (const a of art.attributes || []) {
      const n = bySid(s, a.conceptId);
      const i = n ? n.attrs.findIndex((x) => x.sid === a.id) : -1;
      if (!n || i < 0) continue;
      n.attrs[i] = toAttr(a);
      if (this.ui.drawerNode === n) this.ui.drawerSeq++;
    }
    for (const r of art.relations || []) {
      let l = linkBySid(s, r.id);
      if (!l) {
        if (r.dyingAt) continue;
        const a = bySid(s, r.aId),
          b = bySid(s, r.bId);
        if (!a || !b) continue;
        l = addLink(s, a, b, r.kind, r.rest, r.label, r.seed);
        l.sid = r.id;
        l.pending = r.pending;
        continue;
      }
      l.label = r.label;
      if (l.a.sid !== r.aId || l.b.sid !== r.bId) {
        const a = bySid(s, r.aId),
          b = bySid(s, r.bId);
        if (a && b) {
          l.a = a;
          l.b = b;
        }
      }
      if (regrow) l.grow = { start: now() };
      l.pending = r.pending;
      if (r.dyingAt && !l.dying) {
        const link = l;
        link.dying = { start: now() };
        setTimeout(() => {
          const j = s.links.indexOf(link);
          if (j >= 0) s.links.splice(j, 1);
        }, 700);
      }
    }
    for (const dp of art.domainProducts || []) {
      const d = this.domainBySid(dp.id);
      if (d) this.bindDomain(d, dp);
    }
    for (const src of art.sources || []) {
      const n = bySid(s, src.id);
      if (!n) continue;
      n.label = src.label;
      n.pending = src.pending;
      n.disabled = src.disabled;
      if (src.dyingAt && !n.dying) n.dying = { start: now(), color: RED };
    }
  }

  /**
   * A resolved conflict: the clash line goes, and the renamed definition loses its old "is a"
   * line; the new one arrives with the artefacts. Lines leave at once, as in the reference.
   */
  private resolveConflictLinks(art: Artefacts): void {
    const s = this.s;
    const i = s.links.findIndex((l) => l.kind === 'clash');
    if (i >= 0) s.links.splice(i, 1);
    const renamed = (art.concepts || []).map((c) => ({ n: bySid(s, c.id), c })).find((x) => x.n && x.n.label !== x.c.label)?.n;
    if (!renamed) return;
    const j = s.links.findIndex((l) => l.a === renamed && l.kind === 'isa');
    if (j >= 0) s.links.splice(j, 1);
  }

  /** A line fades for 0.7 s, then leaves the canvas. */
  fadeLink(link: Link | null | undefined): void {
    if (!link || link.dying) return;
    const s = this.s;
    link.dying = { start: now() };
    setTimeout(() => {
      const j = s.links.indexOf(link);
      if (j >= 0) s.links.splice(j, 1);
    }, 700);
  }

  /** Every cell of the company fades, and the company leaves the view 0.8 s later. */
  private removeCompanyLater(c: Company | null): void {
    if (!c) return;
    const s = this.s;
    for (const x of s.nodes) if (x.company === c) x.dying = { start: now(), color: RED };
    setTimeout(() => {
      const i = s.companies.indexOf(c);
      if (i >= 0) s.companies.splice(i, 1);
      s.DOMAINS = s.companies.flatMap((x) => x.domains);
      if (s.activeCompany === c) s.activeCompany = s.companies[0] || null;
      layoutCompanies(s);
      this.renderCompanies();
    }, 800);
  }

  /** A source was enabled, disabled, reconfigured or refreshed: its state and the freshness it feeds. */
  private applySourceChanged(src: Source, feeds: Binding[]): void {
    const s = this.s;
    const n = bySid(s, src.id);
    if (n) {
      n.disabled = src.disabled;
      n.pending = src.pending;
      n.label = src.label;
    }
    for (const b of feeds) {
      const c = bySid(s, b.conceptId);
      if (c && c.bound) c.bound.fresh = b.fresh;
    }
    this.bump();
  }

  /** Domain colours, accent and source colour onto the canvas and the page, the reference's `applyColors`. */
  applyColors(): void {
    const s = this.s;
    const ap = this.ui.appearance;
    if (!ap) return;
    for (const t of DOMAIN_TEMPLATES) {
      const c = ap.colors[t.key] || DEFAULT_COLORS[t.key];
      t.color = c;
      for (const d of s.DOMAINS) if (d.key === t.key) d.color = c;
      for (const n of s.nodes)
        if (n.domain && n.domain.key === t.key) {
          n.finalColor = c;
          if (!n.split && !n.diff) n.color = c;
        }
    }
    document.documentElement.style.setProperty('--accent', ap.accent);
    s.BRASS = ap.source;
    this.bump();
  }

  // ------------------------------------------------------------ captions, toasts

  caption(kicker: string, text: string): void {
    this.ui.caption = { kicker, text, seq: this.ui.caption.seq + 1 };
    this.remember(kicker, text, kicker === 'Not understood');
    this.bump();
  }

  /** Adds an entry to the teach bar history unless it repeats the newest one. */
  private remember(kicker: string, text: string, refused: boolean): void {
    const last = this.ui.history[this.ui.history.length - 1];
    if (last && last.kicker === kicker && last.text === text) return;
    const entry = { seq: ++this.historySeq, kicker, text, refused };
    this.ui.history = [...this.ui.history, entry].slice(-HISTORY_SIZE);
  }

  toast2(strong: string, text: string): void {
    const id = ++this.toastSeq;
    this.ui.toasts = [...this.ui.toasts, { id, strong, text }];
    this.bump();
    setTimeout(() => {
      this.ui.toasts = this.ui.toasts.filter((t) => t.id !== id);
      this.bump();
    }, 3000);
  }

  /** Company selector and teach placeholder follow the active company, whatever the number of companies. */
  renderCompanies(): void {
    const s = this.s;
    this.ui.sayPlaceholder = s.activeCompany ? `Teach ${s.activeCompany.name}…` : '';
    this.bump();
  }

  setActive(c: Company | null): void {
    if (c && c !== this.s.activeCompany) {
      this.s.activeCompany = c;
      this.renderCompanies();
    }
  }

  selectCompany(key: string): void {
    this.s.activeCompany = this.s.companies.find((c) => c.key === key) || this.s.activeCompany;
    this.renderCompanies();
  }

  setSay(value: string): void {
    this.ui.say = value;
    this.bump();
  }

  // ------------------------------------------------------------ proposals

  /** Sends a draft; refusals surface as the reference's toast or caption. */
  async propose(draft: ProposalDraft): Promise<Proposal | null> {
    try {
      return await api.createProposal(draft);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.problem.code === 'cross_company_disabled')
          this.toast2('Not allowed', 'companies may not interact · enable it in the admin portal');
        else if (err.problem.code === 'duplicate_relation' || err.problem.code === 'duplicate_label')
          this.caption('Already there', err.problem.detail || err.problem.title);
        else if (err.status !== 404) this.toast2('Refused', err.problem.detail || err.problem.title);
        return null;
      }
      throw err;
    }
  }

  async approve(p: Proposal): Promise<void> {
    if (!p.ready) return;
    try {
      await api.approve(p.id);
    } catch (err) {
      await this.decisionRefused(err);
    }
  }

  async reject(p: Proposal): Promise<void> {
    try {
      await api.reject(p.id);
    } catch (err) {
      await this.decisionRefused(err);
    }
  }

  /** A proposal decided elsewhere or no longer ready means the panel is stale: reload the scene
   * and its proposals silently. Every other refusal, other 409s included, is the reference's toast. */
  private async decisionRefused(err: unknown): Promise<void> {
    if (err instanceof ApiError && err.status === 409 && STALE_PROPOSAL_CODES.has(err.problem.code))
      await this.reloadScene();
    else this.refused(err);
  }

  async approveAll(): Promise<void> {
    try {
      const res = await api.approveAll();
      this.caption('Approved', res.caption || 'All pending proposals are now part of the model.');
    } catch (err) {
      this.refused(err);
    }
  }

  /** Approves a proposal and the open proposals of its branch, calling again while the API reports
   * the branch incomplete and the last call still approved something. */
  async approveBranch(p: Proposal): Promise<void> {
    if (!p.ready) return;
    try {
      for (let calls = 0; calls < MAX_BRANCH_CALLS; calls++) {
        const res = await api.approveBranch(p.id);
        if (res.complete || res.approved === 0) break;
      }
    } catch (err) {
      await this.decisionRefused(err);
    }
    await this.refreshProposals();
  }

  async rejectAll(): Promise<void> {
    try {
      const res = await api.rejectAll();
      this.caption('Rejected', res.caption || 'All pending proposals were discarded.');
    } catch (err) {
      this.refused(err);
    }
  }

  /** An API refusal (403, 503 for a change kind not served yet or still busy after the client's
   * retry, …) as the reference's toast; anything else is rethrown. */
  refused(err: unknown): void {
    if (!(err instanceof ApiError)) throw err;
    const text = err.problem.detail || err.problem.title;
    this.remember('Refused', text, true);
    this.toast2('Refused', text);
  }

  // ------------------------------------------------------------ toggles

  togglePanel(): void {
    this.ui.panelOff = document.body.classList.toggle('panel-off');
    this.bump();
  }

  toggleLegend(): void {
    this.ui.legendOff = !this.ui.legendOff;
    this.bump();
  }

  toggleDomainsCard(): void {
    this.ui.domainsOff = !this.ui.domainsOff;
    this.bump();
  }

  /** Flips the user's Skip animation choice and remembers it in this browser. */
  toggleSkip(): void {
    this.ui.skipAnimation = !this.ui.skipAnimation;
    writeSkipAnimation(this.ui.skipAnimation);
    this.syncSkip();
    this.bump();
  }

  /** Animations are skipped when the user chose to or the tenant turned them off. */
  syncSkip(): void {
    const st = this.ui.settings;
    this.s.SKIP = this.ui.skipAnimation || (!!st && !st.animations);
  }

  toggleCoverage(): void {
    this.s.COVERAGE = !this.s.COVERAGE;
    this.bump();
    void api.putViewState({ coverage: this.s.COVERAGE }).catch(() => undefined);
  }

  arrange(): void {
    if (!this.renderer) return;
    arrangeCanvas(this.s, this.renderer.v);
    this.bump();
  }

  /** Title of the Arrange button for the current highlighted set. */
  arrangeTitle(): string {
    const s = this.s;
    return s.lineageNode
      ? `Arrange the lineage of ${s.lineageNode.label} (A)`
      : s.cellFocus
        ? `Arrange ${s.cellFocus.label} and its relations (A)`
        : s.domainFocus
          ? `Arrange ${s.domainFocus.name} and what it relates to (A)`
          : 'Lay the model out for reading (A)';
  }

  setTheme(name: 'dark' | 'light', persist = true): void {
    this.ui.theme = name;
    this.renderer?.applyTheme(name);
    document.documentElement.setAttribute('data-theme', name === 'light' ? 'light' : 'dark');
    this.bump();
    if (persist) void api.patchAppearance({ theme: name }).catch(() => undefined);
  }

  toggleTheme(): void {
    this.setTheme(this.ui.theme === 'light' ? 'dark' : 'light');
  }

  openAdmin(page?: string): void {
    if (page) this.ui.adminPage = page;
    this.ui.adminOpen = true;
    this.renderAdmin();
  }

  setAdminPage(page: string): void {
    this.ui.adminPage = page;
    this.renderAdmin();
  }

  /** Re-renders the admin portal from scratch, the reference's `renderAdmin`. */
  renderAdmin(): void {
    this.ui.adminRev++;
    this.bump();
  }

  closeAdmin(): void {
    this.ui.adminOpen = false;
    this.bump();
  }

  /** Mirrors the tenant settings onto the shell, the reference's `applySettings`. */
  applySettings(): void {
    const st = this.ui.settings;
    if (!st) return;
    this.ui.legendOff = !st.legend ? true : this.ui.legendOff;
    this.syncSkip();
    this.bump();
  }

  // ------------------------------------------------------------ domains card

  toggleDomainHidden(d: Domain): void {
    d.hidden = !d.hidden;
    this.s.focusDomain = null;
    this.bump();
    if (d.sid) void api.updateDomainProduct(d.sid, { hidden: d.hidden }).catch(() => undefined);
  }

  focusDomainFromCard(d: Domain): void {
    const s = this.s;
    if (s.focusDomain === d) {
      for (const x of s.DOMAINS) x.hidden = false;
      s.focusDomain = null;
    } else {
      const keep = new Set<Domain>([d]);
      for (const l of s.links) {
        if (l.a.domain === d && l.b.domain) keep.add(l.b.domain);
        if (l.b.domain === d && l.a.domain) keep.add(l.a.domain);
      }
      for (const x of s.DOMAINS) x.hidden = !keep.has(x);
      s.focusDomain = d;
    }
    this.bump();
  }

  toggleAllDomains(): void {
    const s = this.s;
    const allOn = s.DOMAINS.every((d) => !d.hidden);
    for (const d of s.DOMAINS) d.hidden = allOn;
    s.focusDomain = null;
    this.bump();
  }

  toggleCompanyDomains(c: Company): void {
    const s = this.s;
    const live = c.domains.filter((d) => s.nodes.some((n) => n.domain === d && !n.dying));
    const on = live.every((d) => d.hidden);
    for (const d of c.domains) d.hidden = !on;
    s.focusDomain = null;
    this.bump();
  }

  // ------------------------------------------------------------ drawer, lineage, boxes

  openDrawer(n: Node): void {
    const s = this.s;
    this.ui.drawerNode = n;
    this.ui.drawerSeq++;
    if (s.lineageNode && s.lineageNode !== n) {
      if (n.kind === 'concept') this.showLineage(n);
      else this.hideLineage();
    } else if (s.lineageNode === n) this.showLineage(n);
    this.bump();
  }

  closeDrawer(): void {
    const s = this.s;
    this.ui.drawerNode = null;
    this.hideLineage();
    if (s.cellFocus) {
      s.cellFocus = null;
      if (!s.domainFocus) {
        s.stickyFocus = null;
        s.focusSet = null;
      }
    }
    this.bump();
  }

  showLineage(n: Node): void {
    showLineageState(this.s, n);
    this.ui.lineageOn = true;
    this.bump();
  }

  hideLineage(): void {
    hideLineageState(this.s, this.ui.drawerNode);
    this.ui.lineageOn = false;
    this.bump();
  }

  toggleLineage(): void {
    const n = this.ui.drawerNode;
    if (!n) return;
    if (this.s.lineageNode === n) this.hideLineage();
    else this.showLineage(n);
  }

  goTo(n: Node): void {
    const s = this.s;
    this.closeAdmin();
    s.userZoomed = true;
    s.cam.tx = n.x;
    s.cam.ty = n.y;
    s.cam.ts = 1.4;
    s.hover = null;
    if (!s.lineageNode) focusOnCell(s, n);
    this.openDrawer(n);
  }

  private boxPosition(sx: number, sy: number): { left: number; top: number } {
    const v = this.renderer?.v;
    const W = v ? v.W : innerWidth,
      H = v ? v.H : innerHeight;
    const pw = W > 900 && !this.ui.panelOff ? 320 : 0;
    return { left: Math.max(170, Math.min(W - pw - 170, sx)), top: Math.min(sy, H - 230) };
  }

  openNewBox(host: Node, sx: number, sy: number): void {
    this.closeLinkBox();
    this.ui.newBox = { host, ...this.boxPosition(sx, sy) };
    this.bump();
  }

  closeNewBox(): void {
    if (!this.ui.newBox) return;
    this.ui.newBox = null;
    this.bump();
  }

  openLinkBox(a: Node, b: Node, sx: number, sy: number, link: Link | null = null): void {
    const st = this.ui.settings;
    if (!link && a.company !== b.company && st && !st.crossCompany) {
      this.toast2('Not allowed', 'companies may not interact · enable it in the admin portal');
      return;
    }
    if (!link && (a.kind === 'source' || b.kind === 'source')) {
      const src = a.kind === 'source' ? a : b,
        tgt = a.kind === 'source' ? b : a;
      if (tgt.kind === 'concept' && src.sid && tgt.sid) {
        void this.propose({ type: 'bind', sourceId: src.sid, conceptIds: [tgt.sid] });
        this.caption('One proposal', `Binding ${tgt.label} to ${src.label} is waiting for your approval.`);
      }
      return;
    }
    this.closeNewBox();
    this.ui.linkBox = { a, b, link, reverse: false, ...this.boxPosition(sx, sy) };
    this.bump();
  }

  closeLinkBox(): void {
    if (!this.ui.linkBox) return;
    this.ui.linkBox = null;
    this.bump();
  }

  reverseLinkBox(): void {
    if (!this.ui.linkBox) return;
    this.ui.linkBox = { ...this.ui.linkBox, reverse: !this.ui.linkBox.reverse };
    this.bump();
  }

  // ------------------------------------------------------------ keyboard escape

  /** Escape on the canvas: zoom, focus, boxes, drawer and lineage all release. */
  escape(): void {
    const s = this.s;
    s.userZoomed = false;
    s.cellFocus = null;
    focusOnDomain(s, null);
    this.closeNewBox();
    this.closeLinkBox();
    this.closeDrawer();
    this.hideLineage();
  }

  /** Label of a lineage stamp, `dd MMM HH:mm` in en-GB. */
  when(x: Node): string {
    return x.bornAt
      ? x.bornAt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) +
          ' ' +
          x.bornAt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
      : '';
  }

  /** Opens a dialog on top of any open one and returns its id. */
  openDialog(spec: DialogSpec | CustomDialog): number {
    const id = ++this.dialogSeq;
    this.ui.dialogs = [...this.ui.dialogs, { id, ...spec }];
    this.bump();
    return id;
  }

  /** Closes the dialog with this id, or the top one. */
  closeDialog(id?: number): void {
    if (!this.ui.dialogs.length) return;
    const target = id ?? this.ui.dialogs[this.ui.dialogs.length - 1].id;
    this.ui.dialogs = this.ui.dialogs.filter((d) => d.id !== target);
    this.bump();
  }
}

export const store = new StudioStore();
export type { StudioStore };
