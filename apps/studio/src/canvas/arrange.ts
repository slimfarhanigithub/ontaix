/**
 * Arrange: lays the model out for reading. Every arrangement is a layered tree read from left to
 * right (`layered.ts`), with room for each cell's labels and each link's action chip, so no two
 * cells, labels or chips overlap and tree links never cross; the order of children keeps the
 * other links from crossing.
 *
 * With nothing highlighted, each company's birth tree grows from its root to both sides. With a
 * highlighted set (lineage, cell, domain), only that set moves, staged in a clear area to the
 * right of everything else, and the camera fits it. `fitTo`, `tw` and `stageOrigin` are ported
 * from reference/ontaix-studio-reference.html lines 506-511.
 */
import { now } from '../runtime/clock';
import { clamp } from './colour';
import { DOMAIN_R } from './constants';
import { focusOnDomain } from './focus';
import { cellFootprint, chipWidth, estimateWidth, measureWith, type Measure } from './footprint';
import { layoutForest, type LayoutBlock, type LayoutItem, type LayoutLink } from './layered';
import { ancestorsOf, descendantsOf } from './lineage';
import { neighbours, shown, type SceneState } from './state';
import type { Domain, Node } from './types';
import { panelW, type View } from './view';

/** Room between the right edge of everything else and the left edge of a staged set. */
const STAGE_CLEAR = 560;
/** Room kept free between two companies' arranged trees. */
const COMPANY_CLEAR = 420;

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

/**
 * Whole-model layout: each company's birth tree from its root, split between the root's two
 * sides, a source beside the first concept bound to it. Cells left without a living parent hang
 * from their company's root.
 */
export function arrangeAll(s: SceneState, measure: Measure = estimateWidth): void {
  const t = now();
  for (const c of s.companies) if (c.root) c.root.tween = null;
  const companies = s.companies.filter((c) => c.root).sort((a, b) => a.x - b.x);
  const set = new Set<Node>();
  const parent = new Map<number, number>();
  const blocks: LayoutBlock[] = [];
  for (const c of companies) {
    const root = c.root as Node;
    set.add(root);
    blocks.push({ root: root.id, at: [root.x, root.y], sides: 'both' });
  }
  const roots = new Map(companies.map((c) => [c, c.root as Node]));
  for (const n of s.nodes) if (!n.dying && !n.fixed && n.company && roots.has(n.company)) set.add(n);
  for (const n of set) {
    if (n.fixed || !n.company) continue;
    const root = roots.get(n.company) as Node;
    let p: Node | undefined = n.parent;
    if (n.kind === 'source') {
      const l = s.links.find((x) => x.kind === 'bind' && x.a === n && !x.dying && set.has(x.b));
      p = l ? l.b : undefined;
    }
    parent.set(n.id, p && set.has(p) && p.company === n.company ? p.id : root.id);
  }
  if (!blocks.length) return;
  const { pos } = layoutForest({
    items: [...set].map((n) => itemOf(n, measure)),
    parent,
    blocks,
    links: linksAmong(s, set, measure),
    groupRank: groupRank(s),
    budget: set.size > 200 ? 40 : set.size > 100 ? 80 : 400,
    apart: COMPANY_CLEAR,
  });
  for (const n of set) {
    if (n.fixed) continue;
    const [x, y] = pos.get(n.id) as [number, number];
    n.tween = { fx: n.x, fy: n.y, tx: x, ty: y, start: t };
    if (n.kind === 'source') n.anchor = [x, y];
  }
  s.cam.tx = s.cam.ty = 0;
  s.userZoomed = false;
  s.lastInteract = now();
}

/** Arrange acts on the highlighted set: lineage, then cell, then domain, else everything. */
export function arrange(s: SceneState, v: View): void {
  const measure = measureWith(v.ctx);
  if (s.lineageNode) return arrangeLineage(s, v, s.lineageNode, measure);
  if (s.cellFocus) return arrangeCell(s, v, s.cellFocus, measure);
  if (s.domainFocus) return arrangeDomain(s, v, s.domainFocus, measure);
  arrangeAll(s, measure);
}
