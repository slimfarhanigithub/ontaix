/**
 * Arrange: lays the model out for reading. Every arrangement is a layered tree read from left to
 * right (`layered.ts`), with room for each cell's labels and each link's action chip, so no two
 * cells, labels or chips overlap and tree links never cross; the order of children keeps the
 * other links from crossing.
 *
 * With nothing highlighted, each company's tree grows from its root to both sides, every domain
 * product in one region of its own, clear of the others and of their headers. With a
 * highlighted set (lineage, cell, domain), only that set moves, staged in a clear area to the
 * right of everything else, and the camera fits it. `fitTo`, `tw` and `stageOrigin` are ported
 * from reference/ontaix-studio-reference.html lines 506-511.
 */
import { now } from '../runtime/clock';
import { clamp } from './colour';
import { DOMAIN_R } from './constants';
import { focusOnDomain } from './focus';
import { layoutByDomain } from './domainTree';
import { cellFootprint, chipWidth, estimateWidth, measureWith, type Measure } from './footprint';
import { GAP_Y, layoutForest, type LayoutBlock, type LayoutItem, type LayoutLink } from './layered';
import { ancestorsOf, descendantsOf } from './lineage';
import { neighbours, shown, type SceneState } from './state';
import type { Domain, Node } from './types';
import { panelW, type View } from './view';

/** Room between the right edge of everything else and the left edge of a staged set. */
const STAGE_CLEAR = 560;

export function fitTo(s: SceneState, v: View, set: Iterable<Node>, padX = 260, padY = 220): void {
  let x0 = 1e9,
    y0 = 1e9,
    x1 = -1e9,
    y1 = -1e9;
  for (const n of set) {
    const x = n.tween ? n.tween.tx : n.x,
      y = n.tween ? n.tween.ty : n.y;
    x0 = Math.min(x0, x);
    y0 = Math.min(y0, y);
    x1 = Math.max(x1, x);
    y1 = Math.max(y1, y);
  }
  const bw = x1 - x0 + 2 * padX,
    bh = y1 - y0 + 2 * padY;
  s.userZoomed = true;
  s.cam.ts = clamp(Math.min((v.W - panelW(v) - 60) / bw, (v.H - 250) / bh), 0.32, 1.6);
  s.cam.tx = (x0 + x1) / 2;
  s.cam.ty = (y0 + y1) / 2 + 10;
}

export const tw = (n: Node, x: number, y: number, t: number): void => {
  n.tween = { fx: n.x, fy: n.y, tx: x, ty: y, start: t };
};

/** Right edge and vertical middle of every shown cell outside `set`; null when there is none. */
function rest(s: SceneState, set: Set<Node>): { x1: number; y: number } | null {
  let x1 = -1e9,
    y0 = 1e9,
    y1 = -1e9,
    any = false;
  for (const n of s.nodes) {
    if (set.has(n) || n.dying || !shown(n)) continue;
    any = true;
    x1 = Math.max(x1, n.x);
    y0 = Math.min(y0, n.y);
    y1 = Math.max(y1, n.y);
  }
  return any ? { x1, y: (y0 + y1) / 2 } : null;
}

/** An empty area to the right of everything that is not highlighted. */
export function stageOrigin(s: SceneState, set: Set<Node>): [number, number] {
  const r = rest(s, set);
  return r ? [r.x1 + DOMAIN_R * 1.6, r.y] : [0, 0];
}

/** Group key of a cell: its company and domain product. */
const groupOf = (n: Node): string | null => (n.domain ? `${n.domain.company.key}/${n.domain.key}` : null);

/** Siblings keep the ring order of domain products, company by company. */
function groupRank(s: SceneState): (g: string | null) => number {
  const rank = new Map<string, number>();
  s.companies.forEach((c, ci) => c.domains.forEach((d) => rank.set(`${c.key}/${d.key}`, ci * 1000 + d.position)));
  return (g) => (g === null ? -1 : (rank.get(g) ?? 999));
}

function itemOf(n: Node, measure: Measure): LayoutItem {
  const f = cellFootprint(n, measure);
  return { id: n.id, r: Math.max(n.r, n.rt), halfW: f.halfW, up: f.up, down: f.down, group: groupOf(n) };
}

function linksAmong(s: SceneState, set: Set<Node>, measure: Measure): LayoutLink[] {
  const out: LayoutLink[] = [];
  for (const l of s.links)
    if (!l.dying && l.a !== l.b && set.has(l.a) && set.has(l.b))
      out.push({ a: l.a.id, b: l.b.id, chipW: chipWidth(l, measure), seed: l.seed });
  return out;
}

/** Lays out `set` as one block whose positions are then moved into the clear area. */
function stageBlock(
  s: SceneState,
  set: Set<Node>,
  parent: Map<number, number>,
  block: Omit<LayoutBlock, 'at'>,
  measure: Measure,
  t: number,
): void {
  const nodes = [...set];
  const items = nodes.map((n) => itemOf(n, measure));
  const { pos } = layoutForest({
    items,
    parent,
    blocks: [{ ...block, at: [0, 0] }],
    links: linksAmong(s, set, measure),
    groupRank: groupRank(s),
  });
  let x0 = 1e9,
    x1 = -1e9,
    y0 = 1e9,
    y1 = -1e9;
  items.forEach((it) => {
    const [x, y] = pos.get(it.id) as [number, number];
    x0 = Math.min(x0, x - it.halfW);
    x1 = Math.max(x1, x + it.halfW);
    y0 = Math.min(y0, y - it.up);
    y1 = Math.max(y1, y + it.down);
  });
  const r = rest(s, set);
  const dx = r ? r.x1 + STAGE_CLEAR - x0 : -(x0 + x1) / 2,
    dy = (r ? r.y : 0) - (y0 + y1) / 2;
  for (const n of nodes) {
    if (n.fixed) continue;
    const [x, y] = pos.get(n.id) as [number, number];
    tw(n, x + dx, y + dy, t);
  }
}

/** The lineage as a tree from its oldest ancestor on the left to its last descendants on the right. */
export function arrangeLineage(s: SceneState, v: View, n: Node, measure: Measure = estimateWidth): void {
  const t = now();
  const anc = ancestorsOf(n).filter((a) => !a.fixed);
  const desc = descendantsOf(s, n);
  const set = new Set([n, ...anc, ...desc]);
  const parent = new Map<number, number>();
  for (const x of set) if (x.parent && set.has(x.parent)) parent.set(x.id, x.parent.id);
  const top = anc[0] ?? n;
  parent.delete(top.id);
  stageBlock(s, set, parent, { root: top.id, sides: 'right' }, measure, t);
  fitTo(s, v, set);
  s.effects.caption(
    `Lineage of ${n.label}, arranged`,
    `Moved to a clear area: ancestors on the left, descendants to the right, siblings one under another. The rest of the model is untouched and out of the way.`,
  );
}

/** The domain's members as their own trees, each related cell of another domain beside the member it touches. */
export function arrangeDomain(s: SceneState, v: View, d: Domain, measure: Measure = estimateWidth): void {
  const t = now();
  const members = s.nodes.filter((x) => x.domain === d && !x.dying);
  if (!members.length) return;
  const mset = new Set(members);
  const via = new Map<Node, Node>();
  for (const l of s.links) {
    if (l.kind === 'bind' || l.dying) continue;
    const [a, b] = [l.a, l.b];
    if (mset.has(a) && !mset.has(b) && !b.dying && !b.fixed && !via.has(b)) via.set(b, a);
    if (mset.has(b) && !mset.has(a) && !a.dying && !a.fixed && !via.has(a)) via.set(a, b);
  }
  const set = new Set([...members, ...via.keys()]);
  const parent = new Map<number, number>();
  const tops: number[] = [];
  for (const m of members) {
    if (m.parent && mset.has(m.parent)) parent.set(m.id, m.parent.id);
    else tops.push(m.id);
  }
  for (const [x, m] of via) parent.set(x.id, m.id);
  stageBlock(s, set, parent, { root: null, tops, sides: 'right' }, measure, t);
  focusOnDomain(s, d);
  fitTo(s, v, set);
  s.effects.caption(
    `${d.name}, arranged`,
    `Moved to a clear area: ${members.length} concepts of ${d.name} from left to right, the ${via.size} concept${via.size === 1 ? '' : 's'} it relates to beside what they touch. Press Arrange with nothing selected to put everything back.`,
  );
}

/** One cell and everything linked to it: what points to it on the left, what it points to on the right. */
export function arrangeCell(s: SceneState, v: View, n: Node, measure: Measure = estimateWidth): void {
  const t = now();
  const nb = [...neighbours(s, n)].filter((x) => x !== n && !x.dying && !x.fixed);
  nb.sort((a, b) =>
    ((a.domain ? a.domain.name : '') + a.label).localeCompare((b.domain ? b.domain.name : '') + b.label),
  );
  const set = new Set([n, ...nb]);
  const parent = new Map<number, number>();
  const side = new Map<number, -1 | 1>();
  for (const x of nb) {
    parent.set(x.id, n.id);
    const out = s.links.some((l) => l.a === n && l.b === x && !l.dying);
    side.set(x.id, out ? 1 : -1);
  }
  stageBlock(s, set, parent, { root: n.id, sides: 'both', side }, measure, t);
  fitTo(s, v, set);
  s.effects.caption(
    `${n.label} and its relations, arranged`,
    `Moved to a clear area: ${n.label} in the middle, its ${nb.length} linked concept${nb.length === 1 ? '' : 's'} around it, what points to it on the left and what it points to on the right, grouped by domain product. Press Arrange with nothing selected to put everything back.`,
  );
}

/** Zoom under which the renderer stops drawing action chips; cell labels go at 0.45. */
const READABLE = 0.55;

/**
 * Whole-model layout: each company's tree with every domain product in one region of its own
 * (`domainTree.ts`). The camera fits the model; when that fit would be too small for labels and
 * chips to be drawn, it stays at the smallest zoom that draws them, centred on the active
 * company, and the rest is a pan away.
 */
export function arrangeAll(s: SceneState, measure: Measure = estimateWidth, v?: View): void {
  const t = now();
  for (const c of s.companies) if (c.root) c.root.tween = null;
  const companies = s.companies.filter((c) => c.root).sort((a, b) => a.x - b.x);
  if (!companies.length) return;
  const pos = layoutByDomain(s, companies, measure);
  for (const [n, [x, y]] of pos) {
    n.tween = { fx: n.x, fy: n.y, tx: x, ty: y, start: t };
    if (n.kind === 'source') n.anchor = [x, y];
  }
  s.cam.tx = s.cam.ty = 0;
  s.userZoomed = false;
  s.lastInteract = now();
  if (!v) return;
  let x0 = 1e9,
    y0 = 1e9,
    x1 = -1e9,
    y1 = -1e9;
  for (const n of s.nodes) {
    if (n.dying || !shown(n)) continue;
    const x = n.tween ? n.tween.tx : n.x,
      y = n.tween ? n.tween.ty : n.y;
    x0 = Math.min(x0, x);
    y0 = Math.min(y0, y);
    x1 = Math.max(x1, x);
    y1 = Math.max(y1, y);
  }
  // The same fit the physics step makes while the user has not zoomed.
  const fit = Math.min((v.W - panelW(v) - 60) / (x1 - x0 + 2 * (175 + 80)), (v.H - 250) / (y1 - y0 + 2 * (175 + 70)));
  if (fit >= READABLE) return;
  const home = s.activeCompany && s.activeCompany.root ? s.activeCompany : companies[0];
  let hx0 = 1e9,
    hx1 = -1e9,
    hy0 = 1e9,
    hy1 = -1e9;
  for (const n of s.nodes) {
    if (n.dying || !shown(n) || n.company !== home) continue;
    const x = n.tween ? n.tween.tx : n.x,
      y = n.tween ? n.tween.ty : n.y;
    hx0 = Math.min(hx0, x);
    hx1 = Math.max(hx1, x);
    hy0 = Math.min(hy0, y);
    hy1 = Math.max(hy1, y);
  }
  s.userZoomed = true;
  s.cam.ts = READABLE;
  s.cam.tx = (hx0 + hx1) / 2;
  s.cam.ty = (hy0 + hy1) / 2;
}

/** Arrange acts on the highlighted set: lineage, then cell, then domain, else everything. */
export function arrange(s: SceneState, v: View): void {
  const measure = measureWith(v.ctx);
  if (s.lineageNode) return arrangeLineage(s, v, s.lineageNode, measure);
  if (s.cellFocus) return arrangeCell(s, v, s.cellFocus, measure);
  if (s.domainFocus) return arrangeDomain(s, v, s.domainFocus, measure);
  arrangeAll(s, measure, v);
}

/**
 * A cell that changed domain joins its new domain's cluster. A free cell is left to the domain's
 * pull. A cell Arrange placed glides under the lowest arranged cell of its new domain in its
 * company and stays pinned there, so an arranged region stays readable; with no arranged cell
 * in that domain it is released to the domain's pull.
 */
export function settleInDomain(s: SceneState, n: Node, measure: Measure = estimateWidth): void {
  if (!n.pinned && !n.tween) return;
  n.tween = null;
  n.pinned = false;
  const at = (m: Node): [number, number] => (m.tween ? [m.tween.tx, m.tween.ty] : [m.x, m.y]);
  const bottom = (m: Node): number => at(m)[1] + cellFootprint(m, measure).down;
  const peers = s.nodes.filter((m) => m !== n && m.domain === n.domain && m.company === n.company && !m.dying && (m.pinned || !!m.tween));
  if (!peers.length) return;
  const low = peers.reduce((a, b) => (bottom(b) > bottom(a) ? b : a));
  tw(n, at(low)[0], bottom(low) + GAP_Y + cellFootprint(n, measure).up, now());
}
