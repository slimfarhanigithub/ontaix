/**
 * Readability of a laid-out model, measured on the geometry the renderer draws: a link is the
 * quadratic curve of `links.ts`, bent by its seed and trimmed at the two cells; its action chip
 * sits at the middle of the drawn curve, turned along it and kept upright; a cell's labels sit
 * under it. Pure: no scene, no canvas.
 */
import { distSeg, hull, type Pt } from './hulls';

export interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface MetricCell {
  x: number;
  y: number;
  r: number;
  /** The cell and its label block. */
  box: Box;
  /** Domain product the cell belongs to (company and domain); null for none. */
  group: string | null;
}

export interface MetricLink {
  /** Index of the source cell. */
  a: number;
  /** Index of the target cell. */
  b: number;
  /** Curve bend in [0, 1); 0.5 draws a straight line. */
  seed: number;
  /** Width of the action chip; 0 for a link without an action. */
  chipW: number;
}

export interface LayoutMetrics {
  /** Pairs of links whose curves intersect; links that share a cell are not a crossing. */
  crossings: number;
  /** Pairs of cells whose cell-and-label blocks overlap. */
  cellOverlaps: number;
  /** Pairs of action chips that overlap. */
  chipOverlaps: number;
  /** Chip and cell pairs where a chip covers a cell or its labels, its own two cells included. */
  chipsOnCells: number;
  /** Link and cell pairs where a link runs through a cell or its labels without ending there. */
  linksThroughCells: number;
  /** Links with an action that are too short for the renderer to draw their chip. */
  hiddenLabels: number;
  /** Pairs of domain products whose tinted regions overlap. */
  regionOverlaps: number;
  /** Domain headers that cover a cell, its labels, another header or another domain's region. */
  headerOverlaps: number;
}

/** The two-line header the renderer writes above a domain product's region. */
export interface MetricHeader {
  group: string;
  box: Box;
}

/** Shortest visible length of a link (between the two cells) at which its chip is drawn. */
export const CHIP_MIN_GAP = 70;
/** Padding of the tinted domain region around its cells (`drawDomains`). */
export const REGION_PAD = 86;
/** Height of the action chip. */
const CHIP_H = 18;
/** Segments a link curve is cut into for the intersection tests. */
const STEPS = 16;

/** The drawn part of a link: points along the curve, its visible length and its chip. */
export interface LinkShape {
  pts: Pt[];
  /** Distance between the two cells' rims. */
  gap: number;
  /** Chip centre and angle; null when the link draws no chip. */
  chip: { x: number; y: number; ang: number } | null;
}

/** The curve of `links.ts` (`curve`, `qp`, `qt`) between two cell centres, fully grown. */
export function linkShape(
  a: { x: number; y: number; r: number },
  b: { x: number; y: number; r: number },
  seed: number,
  steps = STEPS,
): LinkShape {
  const mx = (a.x + b.x) / 2,
    my = (a.y + b.y) / 2,
    dx = b.x - a.x,
    dy = b.y - a.y,
    k = (seed - 0.5) * 0.3;
  const cx = mx - dy * k,
    cy = my + dx * k;
  const qp = (u: number): Pt => [
    (1 - u) * (1 - u) * a.x + 2 * (1 - u) * u * cx + u * u * b.x,
    (1 - u) * (1 - u) * a.y + 2 * (1 - u) * u * cy + u * u * b.y,
  ];
  const chord = Math.hypot(dx, dy) || 1;
  const u0 = Math.min(Math.max((a.r * 1.05) / chord, 0), 0.45);
  const u1 = Math.min(Math.max(1 - (b.r * 1.05 + 10) / chord, 0.55), 1);
  const pts: Pt[] = [];
  for (let i = 0; i <= steps; i++) pts.push(qp(u0 + ((u1 - u0) * i) / steps));
  const gap = chord - a.r - b.r;
  let chip: LinkShape['chip'] = null;
  if (gap > CHIP_MIN_GAP) {
    const [x, y] = qp((u0 + u1) / 2);
    const tx = 0.5 * (cx - a.x) + 0.5 * (b.x - cx),
      ty = 0.5 * (cy - a.y) + 0.5 * (b.y - cy);
    let ang = Math.atan2(ty, tx);
    if (ang > Math.PI / 2 || ang < -Math.PI / 2) ang += Math.PI;
    chip = { x, y, ang };
  }
  return { pts, gap, chip };
}

/** Corners of a chip of width `w` centred at (x, y) and turned by `ang`. */
export function chipCorners(x: number, y: number, ang: number, w: number, h = CHIP_H): Pt[] {
  const c = Math.cos(ang),
    s = Math.sin(ang),
    hw = w / 2,
    hh = h / 2;
  return [
    [x - hw * c + hh * s, y - hw * s - hh * c],
    [x + hw * c + hh * s, y + hw * s - hh * c],
    [x + hw * c - hh * s, y + hw * s + hh * c],
    [x - hw * c - hh * s, y - hw * s + hh * c],
  ];
}

export const boxCorners = (b: Box): Pt[] => [
  [b.x0, b.y0],
  [b.x1, b.y0],
  [b.x1, b.y1],
  [b.x0, b.y1],
];

/** True when two convex polygons overlap by more than a hair (separating axis test). */
export function convexOverlap(p: Pt[], q: Pt[]): boolean {
  for (const poly of [p, q]) {
    for (let i = 0; i < poly.length; i++) {
      const [x0, y0] = poly[i],
        [x1, y1] = poly[(i + 1) % poly.length];
      const nx = y0 - y1,
        ny = x1 - x0;
      let pmin = Infinity,
        pmax = -Infinity,
        qmin = Infinity,
        qmax = -Infinity;
      for (const [x, y] of p) {
        const d = x * nx + y * ny;
        pmin = Math.min(pmin, d);
        pmax = Math.max(pmax, d);
      }
      for (const [x, y] of q) {
        const d = x * nx + y * ny;
        qmin = Math.min(qmin, d);
        qmax = Math.max(qmax, d);
      }
      const eps = 1e-6 * Math.hypot(nx, ny);
      if (pmax <= qmin + eps || qmax <= pmin + eps) return false;
    }
  }
  return true;
}

const boxesOverlap = (a: Box, b: Box): boolean => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

const orient = (a: Pt, b: Pt, c: Pt): number => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);

/** True when two segments properly cross or touch. */
export function segmentsMeet(p1: Pt, p2: Pt, q1: Pt, q2: Pt): boolean {
  const d1 = orient(q1, q2, p1),
    d2 = orient(q1, q2, p2),
    d3 = orient(p1, p2, q1),
    d4 = orient(p1, p2, q2);
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) return true;
  const on = (a: Pt, b: Pt, c: Pt) =>
    Math.min(a[0], b[0]) <= c[0] && c[0] <= Math.max(a[0], b[0]) && Math.min(a[1], b[1]) <= c[1] && c[1] <= Math.max(a[1], b[1]);
  return (
    (d1 === 0 && on(q1, q2, p1)) || (d2 === 0 && on(q1, q2, p2)) || (d3 === 0 && on(p1, p2, q1)) || (d4 === 0 && on(p1, p2, q2))
  );
}

/** True when a segment meets an axis-aligned box. */
export function segmentHitsBox(p: Pt, q: Pt, b: Box): boolean {
  let t0 = 0,
    t1 = 1;
  const dx = q[0] - p[0],
    dy = q[1] - p[1];
  const clip = (den: number, num: number): boolean => {
    if (den === 0) return num <= 0;
    const t = num / den;
    if (den > 0) {
      if (t > t1) return false;
      if (t > t0) t0 = t;
    } else {
      if (t < t0) return false;
      if (t < t1) t1 = t;
    }
    return true;
  };
  return (
    clip(-dx, p[0] - b.x1) && clip(dx, b.x0 - p[0]) && clip(-dy, p[1] - b.y1) && clip(dy, b.y0 - p[1]) && t0 <= t1
  );
}

const polyBox = (pts: Pt[]): Box => {
  let x0 = Infinity,
    y0 = Infinity,
    x1 = -Infinity,
    y1 = -Infinity;
  for (const [x, y] of pts) {
    x0 = Math.min(x0, x);
    y0 = Math.min(y0, y);
    x1 = Math.max(x1, x);
    y1 = Math.max(y1, y);
  }
  return { x0, y0, x1, y1 };
};

/** True when two polylines meet anywhere. */
export function polylinesMeet(p: Pt[], q: Pt[], pb = polyBox(p), qb = polyBox(q)): boolean {
  if (pb.x1 < qb.x0 || qb.x1 < pb.x0 || pb.y1 < qb.y0 || qb.y1 < pb.y0) return false;
  for (let i = 0; i + 1 < p.length; i++) {
    const a = p[i],
      b = p[i + 1];
    if (Math.max(a[0], b[0]) < qb.x0 || Math.min(a[0], b[0]) > qb.x1) continue;
    if (Math.max(a[1], b[1]) < qb.y0 || Math.min(a[1], b[1]) > qb.y1) continue;
    for (let j = 0; j + 1 < q.length; j++) if (segmentsMeet(a, b, q[j], q[j + 1])) return true;
  }
  return false;
}

/** Index pairs of links whose drawn curves cross; links sharing a cell are skipped. */
export function crossingPairs(cells: MetricCell[], links: MetricLink[], shapes?: LinkShape[]): [number, number][] {
  const sh = shapes ?? links.map((l) => linkShape(cells[l.a], cells[l.b], l.seed));
  const boxes = sh.map((s) => polyBox(s.pts));
  const order = boxes.map((_, i) => i).sort((i, j) => boxes[i].x0 - boxes[j].x0);
  const out: [number, number][] = [];
  for (let oi = 0; oi < order.length; oi++) {
    const i = order[oi];
    for (let oj = oi + 1; oj < order.length; oj++) {
      const j = order[oj];
      if (boxes[j].x0 > boxes[i].x1) break;
      const li = links[i],
        lj = links[j];
      if (li.a === lj.a || li.a === lj.b || li.b === lj.a || li.b === lj.b) continue;
      if (polylinesMeet(sh[i].pts, sh[j].pts, boxes[i], boxes[j])) out.push(i < j ? [i, j] : [j, i]);
    }
  }
  return out;
}

/** The label lines under a cell, without the cell itself. */
const labelBox = (c: MetricCell): Box => ({ x0: c.box.x0, y0: c.y + c.r + 10, x1: c.box.x1, y1: c.box.y1 });

/** What a cell draws: the cell (with its rim) and the label lines under it. */
const parts = (c: MetricCell): Box[] => [
  { x0: c.x - c.r - 2, y0: c.box.y0, x1: c.x + c.r + 2, y1: c.y + c.r + 2 },
  labelBox(c),
];

/** True when a point lies inside a convex polygon (either winding). */
function inConvex(h: Pt[], x: number, y: number): boolean {
  let sign = 0;
  for (let i = 0; i < h.length; i++) {
    const [ax, ay] = h[i],
      [bx, by] = h[(i + 1) % h.length];
    const c = (bx - ax) * (y - ay) - (by - ay) * (x - ax);
    if (c === 0) continue;
    if (sign === 0) sign = Math.sign(c);
    else if (Math.sign(c) !== sign) return false;
  }
  return true;
}

/** Distance between two convex point sets grown into regions; 0 when they overlap. */
export function regionDistance(p: Pt[], q: Pt[]): number {
  if (p.length >= 3 && q.some(([x, y]) => inConvex(p, x, y))) return 0;
  if (q.length >= 3 && p.some(([x, y]) => inConvex(q, x, y))) return 0;
  const edges = (h: Pt[]): [Pt, Pt][] =>
    h.length === 1 ? [[h[0], h[0]]] : h.length === 2 ? [[h[0], h[1]]] : h.map((a, i) => [a, h[(i + 1) % h.length]]);
  let best = Infinity;
  for (const [a, b] of edges(p))
    for (const [c, d] of edges(q)) {
      if (segmentsMeet(a, b, c, d)) return 0;
      best = Math.min(
        best,
        distSeg(a[0], a[1], c[0], c[1], d[0], d[1]),
        distSeg(b[0], b[1], c[0], c[1], d[0], d[1]),
        distSeg(c[0], c[1], a[0], a[1], b[0], b[1]),
        distSeg(d[0], d[1], a[0], a[1], b[0], b[1]),
      );
    }
  return best;
}

/** Every readability measure of a layout. */
export function measureLayout(cells: MetricCell[], links: MetricLink[], headers: MetricHeader[] = []): LayoutMetrics {
  const shapes = links.map((l) => linkShape(cells[l.a], cells[l.b], l.seed));
  const crossings = crossingPairs(cells, links, shapes).length;

  let cellOverlaps = 0;
  const byX = cells.map((_, i) => i).sort((i, j) => cells[i].box.x0 - cells[j].box.x0);
  for (let oi = 0; oi < byX.length; oi++)
    for (let oj = oi + 1; oj < byX.length; oj++) {
      const a = cells[byX[oi]].box,
        b = cells[byX[oj]].box;
      if (b.x0 >= a.x1) break;
      if (!boxesOverlap(a, b)) continue;
      const pa = parts(cells[byX[oi]]),
        pb = parts(cells[byX[oj]]);
      if (pa.some((x) => pb.some((y) => boxesOverlap(x, y)))) cellOverlaps++;
    }

  let hiddenLabels = 0;
  const chips: { poly: Pt[]; box: Box; link: number }[] = [];
  links.forEach((l, i) => {
    if (!l.chipW) return;
    const c = shapes[i].chip;
    if (!c) {
      hiddenLabels++;
      return;
    }
    const poly = chipCorners(c.x, c.y, c.ang, l.chipW);
    chips.push({ poly, box: polyBox(poly), link: i });
  });
  let chipOverlaps = 0;
  for (let i = 0; i < chips.length; i++)
    for (let j = i + 1; j < chips.length; j++)
      if (boxesOverlap(chips[i].box, chips[j].box) && convexOverlap(chips[i].poly, chips[j].poly)) chipOverlaps++;
  let chipsOnCells = 0;
  for (const ch of chips)
    for (const c of cells)
      if (boxesOverlap(ch.box, c.box) && parts(c).some((p) => convexOverlap(ch.poly, boxCorners(p)))) chipsOnCells++;

  let linksThroughCells = 0;
  links.forEach((l, i) => {
    const pts = shapes[i].pts,
      pb = polyBox(pts);
    cells.forEach((c, k) => {
      if (k === l.a || k === l.b || !boxesOverlap(pb, c.box)) return;
      const lb = labelBox(c);
      for (let s = 0; s + 1 < pts.length; s++) {
        const [p, q] = [pts[s], pts[s + 1]];
        if (distSeg(c.x, c.y, p[0], p[1], q[0], q[1]) < c.r || segmentHitsBox(p, q, lb)) {
          linksThroughCells++;
          return;
        }
      }
    });
  });

  const groups = new Map<string, Pt[]>();
  for (const c of cells) {
    if (c.group === null) continue;
    const g = groups.get(c.group);
    if (g) g.push([c.x, c.y]);
    else groups.set(c.group, [[c.x, c.y]]);
  }
  const hullOf = new Map([...groups].map(([g, pts]) => [g, hull(pts)]));
  const hulls = [...hullOf.values()];
  let regionOverlaps = 0;
  for (let i = 0; i < hulls.length; i++)
    for (let j = i + 1; j < hulls.length; j++) if (regionDistance(hulls[i], hulls[j]) < 2 * REGION_PAD) regionOverlaps++;

  let headerOverlaps = 0;
  headers.forEach((h, i) => {
    const hit =
      cells.some((c) => parts(c).some((p) => boxesOverlap(p, h.box))) ||
      headers.some((o, j) => j !== i && boxesOverlap(o.box, h.box)) ||
      [...hullOf].some(([g, hp]) => g !== h.group && regionDistance(hp, boxCorners(h.box)) < REGION_PAD);
    if (hit) headerOverlaps++;
  });

  return { crossings, cellOverlaps, chipOverlaps, chipsOnCells, linksThroughCells, hiddenLabels, regionOverlaps, headerOverlaps };
}
