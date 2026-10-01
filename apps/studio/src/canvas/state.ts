/**
 * The scene state the verbatim renderer modules run on, and the model helpers of
 * reference/ontaix-studio-reference.html lines 250-302 (`addNode`, `addLink`, `find`,
 * `neighbours`, `domainOf`, `domainCentre`, `layoutCompanies`, `addCompany`, `addSource`).
 *
 * The reference keeps these as module-level variables; here they live on one object so that the
 * renderer, the store and the tests can each own an instance.
 */
import { now } from '../runtime/clock';
import { random } from '../runtime/rng';
import { C, CELL, CUSTOM_RING_STEP, DEFAULT_BRASS, DOMAIN_R, DOMAIN_TEMPLATES, TEMPLATE_COUNT } from './constants';
import type { Cam, Company, Domain, Link, LinkKind, Node, SplitInfo } from './types';

/** Side effects the canvas raises toward the shell. Defaults are no-ops so pure tests need none. */
export interface SceneEffects {
  caption(kicker: string, text: string): void;
  arrangeTitle(): void;
  domainsChanged(): void;
  companiesChanged(): void;
}

export interface SceneState {
  nodes: Node[];
  links: Link[];
  companies: Company[];
  DOMAINS: Domain[];
  activeCompany: Company | null;
  nid: number;
  SKIP: boolean;
  COVERAGE: boolean;
  BRASS: string;
  cam: Cam;
  userZoomed: boolean;
  focusSet: Set<Node> | null;
  stickyFocus: Set<Node> | null;
  domainFocus: Domain | null;
  cellFocus: Node | null;
  lineageNode: Node | null;
  lineageSet: Set<Node> | null;
  /** Domain highlighted from the domains card (other domains hidden). */
  focusDomain: Domain | null;
  hover: Node | null;
  dragging: Node | null;
  panning: boolean;
  dropTarget: Node | null;
  lastInteract: number;
  /** A run of proposals is playing; idle drift waits while it is set. */
  running: boolean;
  splitting: Map<Node, SplitInfo>;
  /** Cells picked with Shift+click or Ctrl+click for a bulk deletion; shown as the sticky focus set. */
  selected: Set<Node>;
  effects: SceneEffects;
}

const noEffects: SceneEffects = {
  caption() {},
  arrangeTitle() {},
  domainsChanged() {},
  companiesChanged() {},
};

export function createScene(effects: Partial<SceneEffects> = {}): SceneState {
  return {
    nodes: [],
    links: [],
    companies: [],
    DOMAINS: [],
    activeCompany: null,
    nid: 0,
    SKIP: false,
    COVERAGE: false,
    BRASS: DEFAULT_BRASS,
    cam: { x: 0, y: 0, tx: 0, ty: 0, s: 1, ts: 1 },
    userZoomed: false,
    focusSet: null,
    stickyFocus: null,
    domainFocus: null,
    cellFocus: null,
    lineageNode: null,
    lineageSet: null,
    focusDomain: null,
    hover: null,
    dragging: null,
    panning: false,
    dropTarget: null,
    lastInteract: now(),
    running: false,
    splitting: new Map(),
    selected: new Set(),
    effects: { ...noEffects, ...effects },
  };
}

/** Adds a node; the seed is drawn unless the caller drew it already (`o.seed`). */
export function addNode(s: SceneState, o: Partial<Node>): Node {
  const seed = o.seed ?? random() * 100;
  const n: Node = Object.assign(
    {
      id: s.nid++,
      sid: null,
      x: 0,
      y: 0,
      vx: 0,
      vy: 0,
      rt: CELL,
      r: CELL,
      color: C.root as string,
      finalColor: null,
      cloneColor: null,
      labelAlpha: 1,
      diff: null,
      label: '',
      sub: '',
      kind: 'concept' as const,
      born: now(),
      alpha: 0,
      fixed: false,
      seed,
      conflict: false,
      split: null,
      recoil: null,
      drag: false,
      pinned: false,
      tween: null,
      pending: false,
      flash: null,
      dying: null,
      domain: null,
      company: null,
      bound: null,
      attrs: [],
      anchor: null,
    },
    o,
  );
  s.nodes.push(n);
  return n;
}

/** Adds a link; the curve bend is drawn unless the caller provides the stored `seed`. */
export function addLink(
  s: SceneState,
  a: Node,
  b: Node,
  kind: LinkKind = 'rel',
  rest = 230,
  label = '',
  seed?: number,
): Link {
  const l: Link = {
    sid: null,
    a,
    b,
    kind,
    rest,
    label,
    born: now(),
    pulses: [],
    seed: seed ?? random(),
    alpha: 0,
    grow: null,
    pending: false,
  };
  s.links.push(l);
  return l;
}

/** A node by label inside one company (the active company when `company` is left out). */
export const find = (s: SceneState, label: string, company?: Company | null): Node | null => {
  const c = company === undefined ? s.activeCompany : company;
  return (
    s.nodes.find((n) => n.label.toLowerCase() === label.toLowerCase() && (!c || n.company === c)) || null
  );
};

export const bySid = (s: SceneState, sid: string | null | undefined): Node | null =>
  sid ? s.nodes.find((n) => n.sid === sid) || null : null;

export const linkBySid = (s: SceneState, sid: string | null | undefined): Link | null =>
  sid ? s.links.find((l) => l.sid === sid) || null : null;

export const neighbours = (s: SceneState, n: Node): Set<Node> => {
  const set = new Set([n]);
  for (const l of s.links) {
    if (l.a === n) set.add(l.b);
    if (l.b === n) set.add(l.a);
  }
  return set;
};

export const domainOf = (s: SceneState, key: string | null | undefined, company?: Company | null): Domain | null => {
  const c = company || s.activeCompany;
  return (c ? c.domains : s.DOMAINS).find((d) => d.key === key) || null;
};

export const shown = (n: Node): boolean => !(n.domain && n.domain.hidden);

/**
 * The nine templates sit on the reference's ring, at the reference's angles whatever else the
 * tenant holds. A custom domain (position 9 and up) sits between two templates on the same ring
 * for the first nine, then on outer rings, nine per ring, so no template moves.
 */
export const domainCentre = (d: Domain): [number, number] => {
  const c = d.company;
  if (d.position < TEMPLATE_COUNT) {
    const i = d.position,
      a = -Math.PI / 2 + (i * 2 * Math.PI) / TEMPLATE_COUNT;
    return [c.x + Math.cos(a) * DOMAIN_R, c.y + Math.sin(a) * DOMAIN_R];
  }
  const j = d.position - TEMPLATE_COUNT,
    ring = Math.floor(j / TEMPLATE_COUNT),
    slot = j % TEMPLATE_COUNT,
    a = -Math.PI / 2 + ((slot + 0.5) * 2 * Math.PI) / TEMPLATE_COUNT,
    r = DOMAIN_R + ring * CUSTOM_RING_STEP;
  return [c.x + Math.cos(a) * r, c.y + Math.sin(a) * r];
};

export function layoutCompanies(s: SceneState): void {
  const gap = 2 * DOMAIN_R + 1100;
  s.companies.forEach((c, i) => {
    c.x = (i - (s.companies.length - 1) / 2) * gap;
    c.y = 0;
  });
  for (const n of s.nodes)
    if (n.kind === 'source' && n.company) {
      const a = -Math.PI / 2 + Math.PI / 9 + ((n.ai ?? 0) * Math.PI * 2) / 8;
      n.anchor = [n.company.x + Math.cos(a) * (DOMAIN_R + 360), n.company.y + Math.sin(a) * (DOMAIN_R + 360)];
    }
}

export function addCompany(s: SceneState, name: string, sub: string): Company {
  const c: Company = {
    sid: null,
    key: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
    name,
    sub,
    x: 0,
    y: 0,
    domains: [],
    root: null,
  };
  c.domains = DOMAIN_TEMPLATES.map((t, position) => ({ ...t, sid: null, company: c, version: 1.0, hidden: false, position }));
  s.companies.push(c);
  s.DOMAINS = s.companies.flatMap((x) => x.domains);
  layoutCompanies(s);
  c.root = addNode(s, {
    label: name,
    sub: sub || '',
    kind: 'root',
    color: C.root,
    fixed: true,
    alpha: 1,
    company: c,
    x: c.x,
    y: c.y,
  });
  s.activeCompany = c;
  s.effects.companiesChanged();
  return c;
}

/** What a tenant domain is: the fields every company's product for it copies. */
export interface TenantDomainDef {
  key: string;
  name: string;
  owner: string;
  color: string;
  position: number;
}

/**
 * Gives a company its domain for a tenant domain, or updates the one it has: name, owner, colour
 * and position follow the tenant, everything else (server id, version, hidden) stays. Domains keep
 * ring order, which is also the order of the domains card and the new-concept box.
 */
export function ensureDomain(s: SceneState, c: Company, def: TenantDomainDef): Domain {
  let d = c.domains.find((x) => x.key === def.key);
  if (!d) {
    d = { sid: null, key: def.key, name: def.name, owner: def.owner, color: def.color, company: c, version: 1.0, hidden: false, position: def.position };
    c.domains.push(d);
  } else {
    d.name = def.name;
    d.owner = def.owner;
    d.color = def.color;
    d.position = def.position;
  }
  c.domains.sort((a, b) => a.position - b.position);
  s.DOMAINS = s.companies.flatMap((x) => x.domains);
  return d;
}

export function addSource(s: SceneState, company: Company, label: string, kind: string): Node {
  const i = s.nodes.filter((n) => n.kind === 'source' && n.company === company).length;
  const a = -Math.PI / 2 + Math.PI / 9 + (i * Math.PI * 2) / 8;
  const R = DOMAIN_R + 360;
  const n = addNode(s, {
    label,
    sub: kind || 'system',
    kind: 'source',
    color: s.BRASS,
    company,
    x: company.x + Math.cos(a) * R,
    y: company.y + Math.sin(a) * R,
    r: 16,
    rt: 16,
    anchor: [company.x + Math.cos(a) * R, company.y + Math.sin(a) * R],
    labelAlpha: 1,
  });
  n.ai = i;
  return n;
}

/** Domains of a company that have at least one living cell. */
export const liveOf = (s: SceneState, c: Company): Domain[] =>
  c.domains.filter((d) => s.nodes.some((n) => n.domain === d && !n.dying));
