/**
 * The demo brain: a large example ontology that grows on the canvas, cell by cell, into the shape
 * of a brain, from the model already on the canvas. It is drawn only: nothing goes to the API,
 * nothing is saved, and a reload or Stop brings the real model back where it was.
 *
 * The real cells move into the brain first: each company's root to the top of the brain stem,
 * each concept to the core of its domain's lobe. The demo cells then bud from them, every
 * domain filling one lobe, faster and faster, while the camera pulls back until the whole brain
 * is in view. Once grown, cells light up here and there, like neurons firing.
 */
import { CELL, C, REDUCED } from '../canvas/constants';
import { clamp } from '../canvas/colour';
import type { SceneState } from '../canvas/state';
import type { Company, Node } from '../canvas/types';
import { panelW, type View } from '../canvas/view';
import { brainPoints, growthOrder, LOBE_CENTRES, lobesOf, neighboursOf, seeded, type BrainPoint } from './brainShape';
import { CORE_KEY, namesFor } from './brainVocabulary';

/** A domain the brain gives a lobe to. */
export interface BrainDomain {
  key: string;
  name: string;
  /** Stored (light) colour, drawn through `themedColour`. */
  color: string;
}

export interface BrainCell {
  /** World position once grown. */
  x: number;
  y: number;
  /** Where it buds from: its parent's grown position, or its own for a seed. */
  px: number;
  py: number;
  /** True when the parent is a cell or a real concept, so a birth link joins them. */
  linked: boolean;
  color: string;
  /** Domain key, or CORE_KEY in the brain stem. */
  domain: string;
  label: string;
  /** Seconds after the start when the cell is born. */
  born: number;
  /** In [0, 1): when it fires once the brain is grown. */
  phase: number;
}

export interface BrainDemo {
  cells: BrainCell[];
  /** Real concepts the brain grew from, and the domains it gave a lobe to. */
  realConcepts: number;
  lobes: number;
  /** Further relations between cells, [earlier, later], drawn once the later one is born. */
  links: [number, number][];
  /** Cell radius and distance between neighbours, in world units. */
  radius: number;
  spacing: number;
  /** Seconds the whole growth takes. */
  duration: number;
  /** Bounds of the first i + 1 cells' grown positions, real cells included: x0, y0, x1, y1. */
  bounds: Float64Array;
  start: number;
  pausedAt: number | null;
  pausedFor: number;
  /** When Stop was pressed: the demo fades out, then leaves the scene. */
  ending: number | null;
  reduced: boolean;
  /** Where every real cell and company stood before the demo, to put them back. */
  saved: Map<Node, { x: number; y: number; pinned: boolean }>;
  savedCompanies: Map<Company, { x: number; y: number }>;
}

/** Unit spacing of the brain's points: about 3,100 cells on a large screen, 1,650 on a phone. */
export const SPACING_LARGE = 0.022;
export const SPACING_SMALL = 0.03;
/** World distance between neighbouring cells, and the cells' radius. */
const WORLD_SPACING = 44;
export const BRAIN_CELL = Math.round(CELL * 0.55);
/** Growth time in seconds, and how sharply it speeds up (the count grows as time to this power). */
export const DURATION = 48;
const SPEED_UP = 2.2;
/** Share of cells given one more relation to an earlier neighbour in the same lobe, and across lobes. */
const EXTRA_SAME = 0.24;
const EXTRA_ACROSS = 0.03;
/** How long a fading demo takes to leave. */
export const FADE_OUT = 0.6;
/**
 * Screen room the camera leaves free, in CSS pixels, above the brain (header and demo bar) and
 * below it (tool row and teach bar): above 900 px wide, and at 900 px and under.
 */
const CLEAR_WIDE: [number, number] = [160, 130];
const CLEAR_NARROW: [number, number] = [180, 170];
/** How far the camera may zoom out while the demo is on. */
export const BRAIN_MIN_ZOOM = 0.05;

export interface BrainOptions {
  spacing?: number;
  seed?: number;
  /** Everything at once (Skip animation). */
  instant?: boolean;
  reduced?: boolean;
}

/** The real cells that join the brain: live, shown concepts and roots. */
const realCells = (s: SceneState): Node[] => s.nodes.filter((n) => !n.dying && n.kind !== 'source' && !(n.domain && n.domain.hidden));

/**
 * Plans the brain around the scene's real cells and starts it at `t`: the real cells move to
 * their places in it and the demo is set on the scene. A demo already on is replaced.
 */
export function startBrain(s: SceneState, domains: BrainDomain[], t: number, o: BrainOptions = {}): BrainDemo {
  if (s.brain) finishBrain(s);
  const spacing = o.spacing ?? SPACING_LARGE;
  const pts = brainPoints(spacing, o.seed ?? 7);
  const lobes = lobesOf(pts, domains.length);
  const scale = WORLD_SPACING / spacing;
  const real = realCells(s);
  const roots = real.filter((n) => n.kind === 'root');
  const xs = s.companies.map((c) => c.x);
  const cx = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : 0;
  const cy = -0.08 * scale;
  const world = (p: BrainPoint): [number, number] => [cx + p.x * scale, cy + p.y * scale];

  // Real cells take the points nearest the top of the stem (roots) or their lobe's core.
  const taken = new Set<number>();
  const target = new Map<Node, number>();
  const nearestFree = (ux: number, uy: number, ok: (i: number) => boolean): number => {
    let best = -1,
      bd = Infinity;
    pts.forEach((p, i) => {
      if (taken.has(i) || !ok(i)) return;
      const d = Math.hypot(p.x - ux, p.y - uy);
      if (d < bd) {
        bd = d;
        best = i;
      }
    });
    return best;
  };
  const lobeOfKey = new Map(domains.map((d, i) => [d.key, i]));
  for (const n of roots) {
    const i = nearestFree(0.3, 0.26, (j) => pts[j].part === 'stem');
    if (i >= 0) {
      taken.add(i);
      target.set(n, i);
    }
  }
  const coreOf = (lobe: number): [number, number] => LOBE_CENTRES[lobe] ?? [0, -0.2];
  for (const n of real) {
    if (n.kind === 'root') continue;
    const lobe = n.domain ? (lobeOfKey.get(n.domain.key) ?? -1) : -1;
    const [ux, uy] = lobe >= 0 ? coreOf(lobe) : [0.3, 0.26];
    const i = nearestFree(ux, uy, (j) => (lobe >= 0 ? lobes[j] === lobe : pts[j].part === 'stem'));
    if (i >= 0) {
      taken.add(i);
      target.set(n, i);
    }
  }

  // Seeds: the real cells, and the core of every lobe no real cell is in.
  const seeds = [...taken];
  domains.forEach((_, lobe) => {
    if ([...taken].some((i) => lobes[i] === lobe)) return;
    const [ux, uy] = coreOf(lobe);
    const i = nearestFree(ux, uy, (j) => lobes[j] === lobe);
    if (i >= 0) seeds.push(i);
  });
  if (!seeds.length) seeds.push(nearestFree(0.3, 0.26, (j) => pts[j].part === 'stem'));
  const near = neighboursOf(pts, spacing * 1.6);
  const { order, parent } = growthOrder(pts, near, seeds, (o.seed ?? 7) + 4);

  const rand = seeded((o.seed ?? 7) + 9);
  const names = new Map<string, { next(): string }>();
  const nameOf = (key: string, label: string) => {
    let src = names.get(key);
    if (!src) {
      src = namesFor(key, label, (o.seed ?? 7) + names.size + 20);
      names.set(key, src);
    }
    return src.next();
  };
  const cellAt = new Map<number, number>();
  const cells: BrainCell[] = [];
  const grown = order.filter((i) => !taken.has(i));
  const total = grown.length;
  const duration = o.instant ? 0 : DURATION;
  for (const i of grown) {
    const lobe = lobes[i];
    const d = lobe >= 0 ? domains[lobe] : null;
    const [x, y] = world(pts[i]);
    const p = parent[i];
    const [px, py] = p >= 0 ? world(pts[p]) : [x, y];
    const k = cells.length;
    cells.push({
      x,
      y,
      px,
      py,
      linked: p >= 0,
      color: d ? d.color : C.root,
      domain: d ? d.key : CORE_KEY,
      label: d ? nameOf(d.key, d.name) : nameOf(CORE_KEY, 'Company'),
      born: duration * Math.pow((k + 1) / total, 1 / SPEED_UP),
      phase: rand(),
    });
    cellAt.set(i, k);
  }
  // Further relations, each to an earlier neighbour, mostly within the lobe.
  const links: [number, number][] = [];
  grown.forEach((i, k) => {
    const pick = rand();
    const same = pick < EXTRA_SAME,
      across = !same && pick < EXTRA_SAME + EXTRA_ACROSS;
    if (!same && !across) return;
    const options = near[i].filter((j) => {
      const c = cellAt.get(j);
      return c !== undefined && c < k && j !== parent[i] && (lobes[j] === lobes[i]) === same;
    });
    if (options.length) links.push([cellAt.get(options[Math.floor(rand() * options.length)]) as number, k]);
  });

  // Running bounds, real cells first.
  const bounds = new Float64Array(Math.max(1, cells.length) * 4);
  let x0 = Infinity,
    y0 = Infinity,
    x1 = -Infinity,
    y1 = -Infinity;
  for (const i of target.values()) {
    const [x, y] = world(pts[i]);
    x0 = Math.min(x0, x);
    y0 = Math.min(y0, y);
    x1 = Math.max(x1, x);
    y1 = Math.max(y1, y);
  }
  cells.forEach((c, k) => {
    x0 = Math.min(x0, c.x);
    y0 = Math.min(y0, c.y);
    x1 = Math.max(x1, c.x);
    y1 = Math.max(y1, c.y);
    bounds.set([x0, y0, x1, y1], k * 4);
  });

  const demo: BrainDemo = {
    cells,
    realConcepts: real.filter((n) => n.kind === 'concept').length,
    lobes: domains.length,
    links,
    radius: BRAIN_CELL,
    spacing: WORLD_SPACING,
    duration,
    bounds,
    start: t,
    pausedAt: null,
    pausedFor: 0,
    ending: null,
    reduced: o.reduced ?? REDUCED,
    saved: new Map(real.map((n) => [n, { x: n.x, y: n.y, pinned: n.pinned }])),
    savedCompanies: new Map(s.companies.map((c) => [c, { x: c.x, y: c.y }])),
  };
  // The real cells move into the brain; each root takes its company along.
  for (const [n, i] of target) {
    const [x, y] = world(pts[i]);
    if (n.kind === 'root' && n.company) {
      n.company.x = x;
      n.company.y = y;
    }
    n.tween = { fx: n.x, fy: n.y, tx: x, ty: y, start: t, pin: true };
  }
  s.brain = demo;
  s.userZoomed = false;
  return demo;
}

/** Seconds of growth so far: the time since the start, less the time paused. */
export function brainElapsed(d: BrainDemo, t: number): number {
  return (d.pausedAt ?? t) - d.start - d.pausedFor;
}

/** How many demo cells are born after `e` seconds of growth. */
export function bornBy(d: BrainDemo, e: number): number {
  let lo = 0,
    hi = d.cells.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (d.cells[mid].born <= e) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** How many demo cells are born at `t`. */
export const bornCount = (d: BrainDemo, t: number): number => bornBy(d, brainElapsed(d, t));

/** How many relations the demo has drawn at `t`: one birth link per linked cell and the further ones. */
export function bornLinks(d: BrainDemo, t: number): number {
  const n = bornCount(d, t);
  let k = 0;
  for (let i = 0; i < n; i++) if (d.cells[i].linked) k++;
  for (const [, b] of d.links) if (b < n) k++;
  return k;
}

export const brainGrown = (d: BrainDemo, t: number): boolean => bornCount(d, t) >= d.cells.length;

export function pauseBrain(d: BrainDemo, t: number): void {
  if (d.pausedAt === null) d.pausedAt = t;
}

export function resumeBrain(d: BrainDemo, t: number): void {
  if (d.pausedAt === null) return;
  d.pausedFor += t - d.pausedAt;
  d.pausedAt = null;
}

/** Grows the brain again from its seeds; the real cells stay in it. */
export function replayBrain(s: SceneState, d: BrainDemo, t: number): void {
  d.start = t;
  d.pausedAt = null;
  d.pausedFor = 0;
  s.userZoomed = false;
}

/** Stop: the demo fades out and the real cells go back where they stood. */
export function stopBrain(s: SceneState, t: number): void {
  const d = s.brain;
  if (!d || d.ending !== null) return;
  d.ending = t;
  for (const [c, at] of d.savedCompanies) {
    c.x = at.x;
    c.y = at.y;
  }
  for (const [n, at] of d.saved) {
    if (!s.nodes.includes(n)) continue;
    n.tween = { fx: n.x, fy: n.y, tx: at.x, ty: at.y, start: t, pin: at.pinned };
  }
  s.userZoomed = false;
}

/** Takes the demo off the scene at once. */
export function finishBrain(s: SceneState): void {
  const d = s.brain;
  if (!d) return;
  if (d.ending === null) stopBrain(s, d.start);
  s.brain = null;
}

/** Opacity of the whole demo: 1, then down to 0 over FADE_OUT once stopped. */
export const brainAlpha = (d: BrainDemo, t: number): number => (d.ending === null ? 1 : clamp(1 - (t - d.ending) / FADE_OUT, 0, 1));

/**
 * One frame of the demo: it leaves the scene once faded out, and while the user has not zoomed
 * or panned, the camera keeps every grown cell in view, above the teach bar and beside the
 * changes panel.
 */
export function brainStep(s: SceneState, v: View, t: number): void {
  const d = s.brain;
  if (!d) return;
  if (d.ending !== null && t - d.ending >= FADE_OUT) {
    s.brain = null;
    return;
  }
  if (s.userZoomed || s.dragging || s.panning || d.ending !== null) return;
  if (!d.cells.length) return;
  // Bounds of the cells born so far, the real cells included; the first cell's before any birth.
  const k = Math.max(0, bornCount(d, t) - 1);
  const b = d.bounds;
  const [top, bottom] = v.W > 900 ? CLEAR_WIDE : CLEAR_NARROW;
  const ts = brainFitZoom(d, v, k);
  s.cam.ts = ts;
  s.cam.tx = (b[k * 4] + b[k * 4 + 2]) / 2;
  // The brain's middle sits in the middle of the room between the demo bar and the tool row.
  s.cam.ty = (b[k * 4 + 1] + b[k * 4 + 3]) / 2 - (top - bottom) / 2 / ts;
}

/** The zoom that shows the first `k + 1` cells, the real ones included, in the room the camera leaves free. */
export function brainFitZoom(d: BrainDemo, v: View, k: number): number {
  const b = d.bounds;
  const pad = d.spacing * 2;
  const bw = b[k * 4 + 2] - b[k * 4] + 2 * pad,
    bh = b[k * 4 + 3] - b[k * 4 + 1] + 2 * pad;
  const [top, bottom] = v.W > 900 ? CLEAR_WIDE : CLEAR_NARROW;
  return clamp(Math.min((v.W - panelW(v) - 80) / bw, (v.H - top - bottom) / bh), BRAIN_MIN_ZOOM, 1);
}
