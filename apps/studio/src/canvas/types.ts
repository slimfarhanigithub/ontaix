/**
 * Shapes of the in-memory model the canvas renderer runs on: the same fields the reference keeps
 * on its `nodes`, `links`, `companies` and domain objects, plus the server ids they map to.
 */

/** The nine template domains every tenant starts with. */
export type TemplateKey =
  | 'production'
  | 'supply'
  | 'sales'
  | 'logistics'
  | 'quality'
  | 'maintenance'
  | 'finance'
  | 'people'
  | 'engineering';

/** A tenant domain key: a template key or a custom domain's key (`^[a-z][a-z0-9_]{1,39}$`). */
export type DomainKey = string;

export type NodeKind = 'root' | 'concept' | 'source';
export type LinkKind = 'rel' | 'isa' | 'same' | 'clash' | 'bind';

export interface Company {
  /** Server id; null until the API has answered. */
  sid: string | null;
  key: string;
  name: string;
  sub: string;
  x: number;
  y: number;
  domains: Domain[];
  root: Node | null;
}

export interface Domain {
  sid: string | null;
  key: DomainKey;
  name: string;
  owner: string;
  color: string;
  company: Company;
  version: number;
  hidden: boolean;
  /** Ring position of the tenant domain: 0 to 8 for the templates, 9 to 63 for custom domains. */
  position: number;
}

export interface Bound {
  source: Node;
  records: number;
  fresh: string;
}

export interface Attr {
  sid?: string;
  name: string;
  type: string;
  col: string;
  fill: number;
  /** A taught attribute's value, shown in place of the column; it has no fill. */
  value?: string;
  state: 'approved' | 'proposed';
}

export interface Split {
  from: Node;
  start: number;
  dur: number;
  ang: number;
  broken: boolean;
  kicked: boolean;
  D: number;
  /** Progress 0..1, written each frame for the parent-side throb. */
  p?: number;
}

export interface SplitInfo {
  p: number;
  ang: number;
  broken: boolean;
}

export interface Tween {
  fx: number;
  fy: number;
  tx: number;
  ty: number;
  start: number;
  pin?: boolean;
}

export interface Flash {
  color: string;
  start: number;
  soft?: boolean;
}

export interface Dying {
  start: number;
  color?: string;
}

export interface Node {
  id: number;
  /** Server id of the concept or source; null for cells the API has not answered for yet. */
  sid: string | null;
  x: number;
  y: number;
  vx: number;
  vy: number;
  rt: number;
  r: number;
  color: string;
  finalColor: string | null;
  cloneColor: string | null;
  labelAlpha: number;
  diff: { start: number } | null;
  label: string;
  sub: string;
  kind: NodeKind;
  born: number;
  alpha: number;
  fixed: boolean;
  seed: number;
  conflict: boolean;
  split: Split | null;
  recoil: { start: number; ang: number } | null;
  drag: boolean;
  pinned: boolean;
  tween: Tween | null;
  pending: boolean;
  flash: Flash | null;
  dying: Dying | null;
  domain: Domain | null;
  company: Company | null;
  bound: Bound | null;
  attrs: Attr[];
  anchor: [number, number] | null;
  parent?: Node;
  birthLink?: Link | null;
  bornAt?: Date;
  /** Anchor index of a source around its company. */
  ai?: number;
  disabled?: boolean;
  /** Rule text of a specialisation, shown as the cell's sub once it has settled. */
  _rule?: string;
}

export interface Link {
  sid: string | null;
  a: Node;
  b: Node;
  kind: LinkKind;
  rest: number;
  label: string;
  born: number;
  pulses: unknown[];
  seed: number;
  alpha: number;
  grow: { start: number } | null;
  pending: boolean;
  dying?: { start: number } | null;
  /** Hit area of the label chip, written by the link renderer. */
  _chip?: { x: number; y: number; r: number };
}

export interface Cam {
  x: number;
  y: number;
  tx: number;
  ty: number;
  s: number;
  ts: number;
}
