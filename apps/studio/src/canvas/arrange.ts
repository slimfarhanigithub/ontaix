/**
 * Arrange: a radial tree from the company with sectors by subtree size, or the highlighted set
 * staged in a clear area to the right of everything else. Ported from
 * reference/ontaix-studio-reference.html lines 506-547 (`fitTo`, `tw`, `stageOrigin`,
 * `arrangeLineage`, `arrangeDomain`, `arrangeCell`, `arrange`).
 */
import { now } from '../runtime/clock';
import { clamp } from './colour';
import { DOMAIN_R } from './constants';
import { focusOnDomain } from './focus';
import { ancestorsOf, childrenOf, descendantsOf } from './lineage';
import { domainCentre, neighbours, shown, type SceneState } from './state';
import type { Domain, Node } from './types';
import { panelW, type View } from './view';

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

/** An empty area to the right of everything that is not highlighted. */
export function stageOrigin(s: SceneState, set: Set<Node>): [number, number] {
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
  if (!any) return [0, 0];
  return [x1 + DOMAIN_R * 1.6, (y0 + y1) / 2];
}

/** Ancestors in a column above, descendants as a tree below. */
export function arrangeLineage(s: SceneState, v: View, n: Node): void {
  const t = now();
  const anc = ancestorsOf(n).filter((a) => !a.fixed);
  const desc = descendantsOf(s, n);
  const set = new Set([n, ...anc, ...desc]);
  const depth = (x: Node): number => {
    let d = 0;
    for (const k of childrenOf(s, x)) d = Math.max(d, 1 + depth(k));
    return d;
  };
  const V = 130,
    Hs = 140;
  const [sx, sy] = stageOrigin(s, set);
  const ex = sx,
    ey = sy - ((depth(n) - anc.length) * V) / 2;
  tw(n, ex, ey, t);
  anc.forEach((a, i) => tw(a, ex, ey - V * (anc.length - i), t));
  const leaves = new Map<Node, number>();
  const count = (x: Node): number => {
    const k = childrenOf(s, x);
    const c = k.length ? k.reduce((a, ch) => a + count(ch), 0) : 1;
    leaves.set(x, c);
    return c;
  };
  count(n);
  const place = (x: Node, left: number, d: number): void => {
    const k = childrenOf(s, x);
    let cur = left;
    for (const c of k) {
      const w = (leaves.get(c) as number) * Hs;
      tw(c, cur + w / 2, ey + V * d, t);
      place(c, cur, d + 1);
      cur += w;
    }
  };
  const total = (leaves.get(n) as number) * Hs;
  place(n, ex - total / 2, 1);
  fitTo(s, v, set);
  s.effects.caption(
    `Lineage of ${n.label}, arranged`,
    `Moved to a clear area: ancestors above, descendants below, siblings side by side. The rest of the model is untouched and out of the way.`,
  );
}

/** Members in a tidy spiral, related cells of other domains on an outer ring beside the member they touch. */
export function arrangeDomain(s: SceneState, v: View, d: Domain): void {
  const t = now();
  const members = s.nodes.filter((x) => x.domain === d && !x.dying);
  if (!members.length) return;
  const pre = new Set(members);
  for (const l of s.links) {
    if (l.kind === 'bind') continue;
    if (pre.has(l.a) && !l.b.fixed) pre.add(l.b);
    if (pre.has(l.b) && !l.a.fixed) pre.add(l.a);
  }
  const [cx, cy] = stageOrigin(s, pre);
  members.sort(
    (a, b) =>
      (s.links.some((l) => l.b === a && l.a.domain !== d) ? 0 : 1) -
      (s.links.some((l) => l.b === b && l.a.domain !== d) ? 0 : 1),
  );
  members.forEach((x, k) => {
    const rr = k === 0 ? 0 : 78 * Math.sqrt(k + 0.5),
      a = k * 2.399963;
    tw(x, cx + Math.cos(a) * rr, cy + Math.sin(a) * rr, t);
  });
  const R = 78 * Math.sqrt(members.length + 0.5) + 150;
  const ext: [Node, Node][] = [];
  const mset = new Set(members);
  for (const l of s.links) {
    if (l.kind === 'bind') continue;
    const [a, b] = [l.a, l.b];
    if (mset.has(a) && !mset.has(b) && !b.dying && !b.fixed) ext.push([b, a]);
    if (mset.has(b) && !mset.has(a) && !a.dying && !a.fixed) ext.push([a, b]);
  }
  const seen = new Map<Node, Node>();
  for (const [x, via] of ext) if (!seen.has(x)) seen.set(x, via);
  const placed = [...seen.entries()]
    .map(([x, via]) => {
      const m = via.tween ? { x: via.tween.tx, y: via.tween.ty } : via;
      return { x, ang: Math.atan2(m.y - cy, m.x - cx) };
    })
    .sort((p, q) => p.ang - q.ang);
  const minGap = Math.min(0.55, (2 * Math.PI) / Math.max(placed.length, 1));
  for (let i = 1; i < placed.length; i++)
    if (placed[i].ang - placed[i - 1].ang < minGap) placed[i].ang = placed[i - 1].ang + minGap;
  for (const p of placed) tw(p.x, cx + Math.cos(p.ang) * R, cy + Math.sin(p.ang) * R, t);
  const set = new Set([...members, ...placed.map((p) => p.x)]);
  focusOnDomain(s, d);
  fitTo(s, v, set);
  s.effects.caption(
    `${d.name}, arranged`,
    `Moved to a clear area: ${members.length} concepts of ${d.name} in the centre, the ${placed.length} concept${placed.length === 1 ? '' : 's'} it relates to on the outer ring, next to what they touch. Press Arrange with nothing selected to put everything back.`,
  );
}

/** One cell and everything linked to it: the cell in the middle, its neighbours on a ring grouped by domain product. */
export function arrangeCell(s: SceneState, v: View, n: Node): void {
  const t = now();
  const nb = [...neighbours(s, n)].filter((x) => x !== n && !x.dying && !x.fixed);
  const set = new Set([n, ...nb]);
  const [cx, cy] = stageOrigin(s, set);
  nb.sort((a, b) =>
    ((a.domain ? a.domain.name : '') + a.label).localeCompare((b.domain ? b.domain.name : '') + b.label),
  );
  const R = Math.max(170, nb.length * 26);
  if (!n.fixed) tw(n, cx, cy, t);
  nb.forEach((x, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / nb.length;
    tw(x, cx + Math.cos(a) * R, cy + Math.sin(a) * R, t);
  });
  fitTo(s, v, set);
  s.effects.caption(
    `${n.label} and its relations, arranged`,
    `Moved to a clear area: ${n.label} in the middle, its ${nb.length} linked concept${nb.length === 1 ? '' : 's'} around it, grouped by domain product. Press Arrange with nothing selected to put everything back.`,
  );
}

/** Whole-model layout: each domain in a spiral around its centre, parents first. */
export function arrangeAll(s: SceneState): void {
  const t = now();
  for (const c of s.companies) if (c.root) c.root.tween = null;
  for (const d of s.DOMAINS) {
    const members = s.nodes.filter((n) => n.domain === d && !n.dying);
    if (!members.length) continue;
    const [cx, cy] = domainCentre(d);
    members.sort(
      (a, b) =>
        (s.links.some((l) => l.b === a && l.a.domain !== d) ? 0 : 1) -
        (s.links.some((l) => l.b === b && l.a.domain !== d) ? 0 : 1),
    );
    members.forEach((n, k) => {
      const rr = k === 0 ? 0 : 70 * Math.sqrt(k + 0.5),
        a = k * 2.399963;
      n.tween = { fx: n.x, fy: n.y, tx: cx + Math.cos(a) * rr, ty: cy + Math.sin(a) * rr, start: t };
    });
  }
  for (const n of s.nodes)
    if (!n.domain && !n.fixed && !n.dying)
      n.tween = { fx: n.x, fy: n.y, tx: n.company ? n.company.x : 0, ty: n.company ? n.company.y : 0, start: t };
  s.cam.tx = s.cam.ty = 0;
  s.userZoomed = false;
  s.lastInteract = now();
}

/** Arrange acts on the highlighted set: lineage, then cell, then domain, else everything. */
export function arrange(s: SceneState, v: View): void {
  if (s.lineageNode) return arrangeLineage(s, v, s.lineageNode);
  if (s.cellFocus) return arrangeCell(s, v, s.cellFocus);
  if (s.domainFocus) return arrangeDomain(s, v, s.domainFocus);
  arrangeAll(s);
}

/** Spiral placement of the k-th member of a domain cluster in the whole-model layout. */
export function spiralPlacement(k: number, cx: number, cy: number, radiusStep = 70): [number, number] {
  const rr = k === 0 ? 0 : radiusStep * Math.sqrt(k + 0.5),
    a = k * 2.399963;
  return [cx + Math.cos(a) * rr, cy + Math.sin(a) * rr];
}
