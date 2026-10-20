/**
 * The demo brain: a large example ontology that grows on the canvas into the shape of a brain,
 * in three acts. It is drawn only: nothing goes to the API, nothing is saved, and a reload or
 * Stop brings the real model back where it was.
 *
 * A company that already holds concepts is the brain's starting point: its model stands as it
 * is, close up, then the root moves to the top of the brain stem and every concept joins the lobe
 * of its domain while the camera pulls back, and the brain grows on from them. A company with no
 * concept yet stands alone at the top of the brain stem, close up, then three domains bud from its
 * root one after another, each with a few named concepts, their relations drawn one by one and a
 * few relations across the domains, while the camera stays close enough to read every name; then
 * the camera pulls back and the story cells fly to the cores of their lobes. Either way the rest
 * of the brain grows fast, faster and faster, every domain filling one lobe of a side view of a
 * brain whose faint outline shows from the start of the pull-back. Once grown, the brain holds
 * still. Cells of other companies fade out and stay set aside until Stop.
 */
import { CELL, C, DOMAIN_TEMPLATES, REDUCED } from '../canvas/constants';
import { clamp, ease } from '../canvas/colour';
import type { SceneState } from '../canvas/state';
import type { Company, Node } from '../canvas/types';
import { panelW, type View } from '../canvas/view';
import { brainPoints, growthOrder, LOBE_CENTRES, lobesOf, neighboursOf, seeded, STEM_TOP, type BrainPoint } from './brainShape';
import { CORE_KEY, namesFor } from './brainVocabulary';

/** A domain the brain gives a lobe to. */
export interface BrainDomain {
  key: string;
  name: string;
  /** Stored (light) colour, drawn through `themedColour`. */
  color: string;
}

/** Where a story cell stands beside the company before it flies into the brain. */
export interface StoryPlace {
  x: number;
  y: number;
  r: number;
  /** Index of the story cell it buds from, or -1 for the company's root. */
  parent: number;
  /** True for a domain, false for one of its concepts. */
  hub: boolean;
}

export interface BrainCell {
  /** World position in the brain. */
  x: number;
  y: number;
  /** Where it buds from in the brain: its parent's position, or its own for a seed. */
  px: number;
  py: number;
  /** True when it buds from a cell or the company's root, so a birth link joins them. */
  linked: boolean;
  color: string;
  /** Domain key, or CORE_KEY in the brain stem. */
  domain: string;
  label: string;
  /** Seconds after the start when the cell is born. */
  born: number;
  /** The story cells of the second act carry their place beside the company; null for the rest. */
  story: StoryPlace | null;
}

/** A further relation: [earlier cell, later cell, seconds after the start when it is drawn]. */
export type BrainLink = [number, number, number];

/** What the demo is showing. */
export type BrainPhase = 'company' | 'domains' | 'brain' | 'grown';

export interface BrainDemo {
  cells: BrainCell[];
  /** The first `stories` cells are the story cells of the second act. */
  stories: number;
  /** Domains the brain gives a lobe to, and how many of them the story grows. */
  lobes: number;
  storyDomains: number;
  /** Further relations, in the order they are drawn. */
  links: BrainLink[];
  /** Cell radius and distance between neighbours in the brain, in world units. */
  radius: number;
  spacing: number;
  /** The company the demo starts from, and its root; null on a canvas with no company. */
  company: string | null;
  root: Node | null;
  /** The root's place at the top of the brain stem. */
  rootAt: { x: number; y: number } | null;
  /** The company's real concepts that join the brain, each with its place in its lobe. */
  joined: Map<Node, { x: number; y: number }>;
  /** Seconds after the start when the third act begins, when the brain cells start budding, and when the brain is grown. */
  act3: number;
  growAt: number;
  duration: number;
  /** Bounds of the whole grown brain, the root included: x0, y0, x1, y1. */
  box: [number, number, number, number];
  start: number;
  /** When the demo was turned on: the other real cells fade out from then. */
  began: number;
  pausedAt: number | null;
  pausedFor: number;
  /** When Stop was pressed: the demo fades out, then leaves the scene. */
  ending: number | null;
  /** Everything at once (Skip animation), and the reduced-motion drawing. */
  instant: boolean;
  reduced: boolean;
  /** The real cells set aside while the demo is on, with no place in the brain, and how far they have faded out (0 to 1). */
  aside: Set<Node>;
  veil: number;
  /** Where every real cell and company stood before the demo, to put them back. */
  saved: Map<Node, { x: number; y: number; pinned: boolean }>;
  savedCompanies: Map<Company, { x: number; y: number }>;
}

/** Unit spacing of the brain's points: about 3,400 cells on a large screen, 1,800 on a phone. */
export const SPACING_LARGE = 0.022;
export const SPACING_SMALL = 0.03;
/** World distance between neighbouring cells, and the cells' radius. */
const WORLD_SPACING = 44;
export const BRAIN_CELL = Math.round(CELL * 0.55);
/** How many domains the story grows, and how many lobes the brain fills at least. */
export const STORY_DOMAINS = 3;
const MIN_LOBES = DOMAIN_TEMPLATES.length;
/** Concepts each story domain grows: fewer on a phone, so the names stay readable. */
const STORY_CONCEPTS = 6;
const STORY_CONCEPTS_SMALL = 4;
/** First act: seconds the company stands alone. */
export const ACT_ONE = 2.4;
/** Second act: seconds before a domain's first concept, between its concepts, and after its last one. */
const HUB_GAP = 0.7;
const CONCEPT_GAP = 0.42;
const DOMAIN_GAP = 0.4;
/** Seconds between the relations across domains, and the pause before the third act. */
const CROSS_GAP = 0.6;
const HOLD = 1.0;
/** How long a story relation takes to reach its second cell once its time has come. */
export const LINK_DRAW = 0.5;
/** Third act: how long the story cells fly into the brain, and the camera pulls back. */
export const MIGRATE = 1.6;
export const ZOOM_OUT = 2.6;
/** Third act: seconds before the first brain cell, the growth time, and how sharply it speeds up. */
const GROW_DELAY = 0.6;
/** Seconds a real cell takes to reach its place in the brain: the canvas's own tween. */
const JOIN = 1.3;
/** Least distance between two real cells in the brain, in neighbour distances, so canvas-sized cells never touch. */
const JOIN_GAP = 1.9;
export const GROW = 10;
const SPEED_UP = 1.5;
/** Story layout beside the root, in world units: domain distance, concept distance and arc. */
const HUB_R = 250;
const CONCEPT_R = 165;
const ARC = (160 * Math.PI) / 180;
const HUB_R_SMALL = 190;
const CONCEPT_R_SMALL = 130;
const ARC_SMALL = (130 * Math.PI) / 180;
/** On a phone the story stands taller than wide, to use the screen's height. */
const TALL_SMALL = 1.4;
/** Story cells' radius: a domain is as large as a concept on the canvas, a concept a little smaller. */
const STORY_HUB = CELL;
const STORY_CONCEPT = Math.round(CELL * 0.75);
/** Share of brain cells given one more relation to an earlier neighbour in the same lobe, and across lobes. */
const EXTRA_SAME = 0.24;
const EXTRA_ACROSS = 0.03;
/** How long the other real cells take to fade out, and how long a stopped demo takes to leave. */
const VEIL_IN = 0.6;
export const FADE_OUT = 0.6;
/**
 * Screen room the camera leaves free, in CSS pixels, above the demo (header and demo bar) and
 * below it (tool row and teach bar): above 900 px wide, and at 900 px and under.
 */
const CLEAR_WIDE: [number, number] = [160, 130];
const CLEAR_NARROW: [number, number] = [180, 170];
/** How far the camera may zoom out while the demo is on, and how close it comes to the story. */
export const BRAIN_MIN_ZOOM = 0.05;
const STORY_MIN_ZOOM = 0.3;

export interface BrainOptions {
  spacing?: number;
  seed?: number;
  /** A phone or a touch screen: fewer story concepts, laid out closer. */
  small?: boolean;
  /** Everything at once (Skip animation). */
  instant?: boolean;
  reduced?: boolean;
}

/**
 * The domains the brain gives a lobe to: the shown tenant domains first, so the story grows the
 * first three of them, then templates the tenant does not hold until the brain has nine lobes.
 * `held` holds every tenant domain key, hidden ones included, so a hidden domain gets no lobe.
 */
export function brainDomains(shown: BrainDomain[], held: Set<string>): BrainDomain[] {
  const out = [...shown];
  for (const t of DOMAIN_TEMPLATES) {
    if (out.length >= MIN_LOBES) break;
    if (!held.has(t.key) && !out.some((d) => d.key === t.key)) out.push({ key: t.key, name: t.name, color: t.color });
  }
  return out;
}

/**
 * Plans the brain around the company and starts it at `t`: the company's concepts take places in
 * the lobes of their domains, every other real cell is set aside, the root heads for the top of
 * the brain stem and the demo is set on the scene. A demo already on is replaced.
 */
export function startBrain(s: SceneState, domains: BrainDomain[], t: number, o: BrainOptions = {}): BrainDemo {
  if (s.brain) finishBrain(s);
  const seed = o.seed ?? 7;
  const spacing = o.spacing ?? SPACING_LARGE;
  const pts = brainPoints(spacing, seed);
  const lobes = lobesOf(pts, domains.length);
  const scale = WORLD_SPACING / spacing;
  const xs = s.companies.map((c) => c.x);
  const cx = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : 0;
  const cy = -0.08 * scale;
  const world = (p: BrainPoint): [number, number] => [cx + p.x * scale, cy + p.y * scale];

  const real = s.nodes.filter((n) => !n.dying);
  // The brain builds on the company being taught when it holds concepts, else on the first one
  // that does; on a canvas with no concept it starts from the company being taught, or the first.
  const live = s.companies.filter((c) => c.root && !c.root.dying);
  const holds = (c: Company) => real.some((n) => n.kind === 'concept' && n.company === c);
  const active = live.find((c) => c === s.activeCompany) ?? null;
  const company = (active && holds(active) ? active : live.find(holds)) ?? active ?? live[0] ?? null;
  const root = company?.root ?? null;
  const aside = new Set<Node>();
  const own: Node[] = [];
  for (const n of real) {
    if (n === root) continue;
    if (company && n.kind === 'concept' && n.company === company) own.push(n);
    else aside.add(n);
  }

  const taken = new Set<number>();
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
    if (best >= 0) taken.add(best);
    return best;
  };
  const stemTop = nearestFree(STEM_TOP[0], STEM_TOP[1], (j) => pts[j].part === 'stem');
  const [rx, ry] = stemTop >= 0 ? world(pts[stemTop]) : [cx, cy];
  const coreOf = (lobe: number): [number, number] => LOBE_CENTRES[lobe] ?? [0, -0.2];

  // The company's concepts join the brain, oldest first, so a parent sits nearer its lobe's core
  // than its children. A concept of no domain joins the stem; one whose domain has no lobe (a
  // hidden domain) is set aside.
  const joined = new Map<Node, { x: number; y: number }>();
  const joinedPoints: number[] = [];
  const apart = (j: number) => joinedPoints.every((k) => Math.hypot(pts[j].x - pts[k].x, pts[j].y - pts[k].y) >= spacing * JOIN_GAP);
  for (const n of own.slice().sort((a, b) => a.born - b.born || a.id - b.id)) {
    const lobe = n.domain ? domains.findIndex((x) => x.key === n.domain?.key) : -1;
    if (n.domain && lobe < 0) {
      aside.add(n);
      continue;
    }
    const [ux, uy] = lobe >= 0 ? coreOf(lobe) : STEM_TOP;
    const inLobe = (j: number) => lobes[j] === lobe;
    let i = nearestFree(ux, uy, (j) => inLobe(j) && apart(j));
    if (i < 0) i = nearestFree(ux, uy, inLobe);
    if (i < 0) {
      aside.add(n);
      continue;
    }
    joinedPoints.push(i);
    const [x, y] = world(pts[i]);
    joined.set(n, { x, y });
  }

  // Names come from one source per domain, so the brain never repeats a story name.
  const names = new Map<string, { next(): string }>();
  const nameOf = (key: string, label: string) => {
    let src = names.get(key);
    if (!src) {
      src = namesFor(key, label, seed + names.size + 20);
      names.set(key, src);
    }
    return src.next();
  };

  // Second act: the story cells, beside the root, each with its place in its lobe's core.
  const cells: BrainCell[] = [];
  const links: BrainLink[] = [];
  // A company with concepts of its own needs no story: its model is the story.
  const story = joined.size ? [] : domains.slice(0, STORY_DOMAINS);
  const perDomain = o.small ? STORY_CONCEPTS_SMALL : STORY_CONCEPTS;
  const hubR = o.small ? HUB_R_SMALL : HUB_R,
    conceptR = o.small ? CONCEPT_R_SMALL : CONCEPT_R,
    arc = o.small ? ARC_SMALL : ARC;
  const pointOf = new Map<number, number>();
  let clock = ACT_ONE;
  const concepts: number[][] = [];
  story.forEach((d, k) => {
    // Three domains stand up left, up right and below the root.
    const angle = story.length === 1 ? -Math.PI / 2 : (-5 * Math.PI) / 6 + (k * 2 * Math.PI) / story.length;
    const tall = o.small ? TALL_SMALL : 1;
    const ax = Math.cos(angle),
      ay = Math.sin(angle) * tall;
    const hx = rx + ax * hubR,
      hy = ry + ay * hubR;
    const hubPoint = nearestFree(...coreOf(k), (j) => lobes[j] === k);
    const [bx, by] = hubPoint >= 0 ? world(pts[hubPoint]) : [hx, hy];
    const hub = cells.length;
    if (hubPoint >= 0) pointOf.set(hubPoint, hub);
    cells.push({
      x: bx,
      y: by,
      px: rx,
      py: ry,
      linked: !!root,
      color: d.color,
      domain: d.key,
      label: d.name,
      born: clock,
      story: { x: hx, y: hy, r: STORY_HUB, parent: -1, hub: true },
    });
    clock += HUB_GAP;
    const mine: number[] = [];
    for (let i = 0; i < perDomain; i++) {
      const a = angle + (perDomain > 1 ? (i / (perDomain - 1) - 0.5) * arc : 0);
      const point = nearestFree(...coreOf(k), (j) => lobes[j] === k);
      const [gx, gy] = point >= 0 ? world(pts[point]) : [hx, hy];
      const idx = cells.length;
      if (point >= 0) pointOf.set(point, idx);
      cells.push({
        x: gx,
        y: gy,
        px: bx,
        py: by,
        linked: true,
        color: d.color,
        domain: d.key,
        label: nameOf(d.key, d.name),
        born: clock,
        story: { x: hx + Math.cos(a) * conceptR, y: hy + Math.sin(a) * conceptR * tall, r: STORY_CONCEPT, parent: hub, hub: false },
      });
      // Every second concept is related to the one before it.
      if (i % 2 === 1) links.push([idx - 1, idx, clock + 0.35]);
      mine.push(idx);
      clock += CONCEPT_GAP;
    }
    concepts.push(mine);
    clock += DOMAIN_GAP;
  });
  // Relations across domains: the two nearest concepts of each pair of neighbouring domains.
  for (let k = 0; k < concepts.length && concepts.length > 1; k++) {
    const a = concepts[k],
      b = concepts[(k + 1) % concepts.length];
    if (concepts.length === 2 && k === 1) break;
    let best: [number, number] = [a[0], b[0]],
      bd = Infinity;
    for (const i of a)
      for (const j of b) {
        const si = cells[i].story as StoryPlace,
          sj = cells[j].story as StoryPlace;
        const dd = Math.hypot(si.x - sj.x, si.y - sj.y);
        if (dd < bd) {
          bd = dd;
          best = [Math.min(i, j), Math.max(i, j)];
        }
      }
    links.push([best[0], best[1], clock]);
    clock += CROSS_GAP;
  }
  const stories = cells.length;
  const act3 = stories ? clock + HOLD : ACT_ONE;

  // Third act: the rest of the brain grows from the root, the story cells, the joined concepts and
  // the core of every lobe none of them reached.
  const seeds = [...taken];
  const reached = new Set(seeds.map((i) => lobes[i]));
  domains.forEach((_, lobe) => {
    if (reached.has(lobe)) return;
    const i = nearestFree(...coreOf(lobe), (j) => lobes[j] === lobe);
    if (i >= 0) {
      taken.delete(i);
      seeds.push(i);
    }
  });
  const near = neighboursOf(pts, spacing * 1.6);
  const { order, parent } = growthOrder(pts, near, seeds, seed + 4);
  const grown = order.filter((i) => !taken.has(i));
  const total = grown.length;
  // Joined concepts reach their places before the first brain cell buds from them.
  const g0 = act3 + (joined.size ? JOIN : GROW_DELAY);
  for (const [k, i] of grown.entries()) {
    const lobe = lobes[i];
    const d = lobe >= 0 ? domains[lobe] : null;
    const [x, y] = world(pts[i]);
    const p = parent[i];
    const [px, py] = p >= 0 ? world(pts[p]) : [x, y];
    pointOf.set(i, cells.length);
    cells.push({
      x,
      y,
      px,
      py,
      linked: p >= 0,
      color: d ? d.color : C.root,
      domain: d ? d.key : CORE_KEY,
      label: d ? nameOf(d.key, d.name) : nameOf(CORE_KEY, 'Company'),
      born: g0 + GROW * Math.pow((k + 1) / total, 1 / SPEED_UP),
      story: null,
    });
  }
  // Further relations in the brain, each to an earlier neighbour, mostly within the lobe.
  const rand = seeded(seed + 9);
  for (const i of grown) {
    const k = pointOf.get(i) as number;
    const pick = rand();
    const same = pick < EXTRA_SAME,
      across = !same && pick < EXTRA_SAME + EXTRA_ACROSS;
    if (!same && !across) continue;
    const options = near[i].filter((j) => {
      const c = pointOf.get(j);
      return c !== undefined && c < k && j !== parent[i] && (lobes[j] === lobes[i]) === same;
    });
    if (options.length) links.push([pointOf.get(options[Math.floor(rand() * options.length)]) as number, k, cells[k].born]);
  }
  links.sort((a, b) => a[2] - b[2]);

  let x0 = rx,
    y0 = ry,
    x1 = rx,
    y1 = ry;
  for (const c of [...cells, ...joined.values()]) {
    x0 = Math.min(x0, c.x);
    y0 = Math.min(y0, c.y);
    x1 = Math.max(x1, c.x);
    y1 = Math.max(y1, c.y);
  }

  const duration = Math.max(act3 + (joined.size ? JOIN : MIGRATE), total ? g0 + GROW : act3);
  const instant = !!o.instant;
  const demo: BrainDemo = {
    cells,
    stories,
    lobes: domains.length,
    storyDomains: story.length,
    links,
    radius: BRAIN_CELL,
    spacing: WORLD_SPACING,
    company: company?.name ?? null,
    root,
    rootAt: root ? { x: rx, y: ry } : null,
    joined,
    act3,
    growAt: g0,
    duration,
    box: [x0, y0, x1, y1],
    start: instant ? t - duration : t,
    began: instant ? t - VEIL_IN : t,
    pausedAt: null,
    pausedFor: 0,
    ending: null,
    instant,
    reduced: o.reduced ?? REDUCED,
    aside,
    veil: instant ? 1 : 0,
    saved: new Map(real.map((n) => [n, { x: n.x, y: n.y, pinned: n.pinned }])),
    savedCompanies: new Map(s.companies.map((c) => [c, { x: c.x, y: c.y }])),
  };
  // The company follows its root to the top of the stem; the cells set aside stay where they are.
  if (root && company) {
    company.x = rx;
    company.y = ry;
  }
  for (const n of aside) n.tween = { fx: n.x, fy: n.y, tx: n.x, ty: n.y, start: t, pin: true };
  moveIntoBrain(demo);
  s.brain = demo;
  s.userZoomed = false;
  return demo;
}

/**
 * Sets the root and the joined concepts on their way into the brain from where they stood before
 * the demo: the root at once when the company stands alone, the root and its concepts together at
 * the third act otherwise; already in place when the demo grows at once.
 */
function moveIntoBrain(d: BrainDemo): void {
  const moves: [Node, { x: number; y: number }][] = [...d.joined];
  if (d.root && d.rootAt) moves.push([d.root, d.rootAt]);
  const leave = d.start + (d.joined.size ? d.act3 : 0);
  for (const [n, to] of moves) {
    if (d.instant) {
      n.tween = null;
      n.x = to.x;
      n.y = to.y;
      n.vx = n.vy = 0;
      n.pinned = true;
      continue;
    }
    const from = d.saved.get(n) ?? { x: n.x, y: n.y };
    n.x = from.x;
    n.y = from.y;
    n.tween = { fx: from.x, fy: from.y, tx: to.x, ty: to.y, start: leave, pin: true };
  }
}

/** Seconds of the demo so far: the time since the start, less the time paused. */
export function brainElapsed(d: BrainDemo, t: number): number {
  return (d.pausedAt ?? t) - d.start - d.pausedFor;
}

/** How many demo cells are born after `e` seconds. */
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

/** How many further relations are drawn after `e` seconds. */
export function linksBy(d: BrainDemo, e: number): number {
  let lo = 0,
    hi = d.links.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (d.links[mid][2] <= e) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** How many demo cells are born at `t`. */
export const bornCount = (d: BrainDemo, t: number): number => bornBy(d, brainElapsed(d, t));

/** How many relations the demo has drawn at `t`: one birth link per linked cell and the further ones. */
export function bornLinks(d: BrainDemo, t: number): number {
  const e = brainElapsed(d, t);
  const n = bornBy(d, e);
  let k = 0;
  for (let i = 0; i < n; i++) if (d.cells[i].linked) k++;
  return k + linksBy(d, e);
}

/** How many domains have grown at `t`. */
export function bornDomains(d: BrainDemo, t: number): number {
  const e = brainElapsed(d, t);
  if (e >= d.growAt) return d.lobes;
  let k = 0;
  for (let i = 0; i < d.stories; i++) if (d.cells[i].story?.hub && d.cells[i].born <= e) k++;
  return k;
}

export const brainGrown = (d: BrainDemo, t: number): boolean => brainElapsed(d, t) >= d.duration;

/** What the demo shows at `t`: the company alone, the story domains, the growing brain, or the grown brain. */
export function brainPhase(d: BrainDemo, t: number): BrainPhase {
  const e = brainElapsed(d, t);
  if (e >= d.duration) return 'grown';
  if (e >= d.act3) return 'brain';
  return d.stories && e >= ACT_ONE ? 'domains' : 'company';
}

/** How far the story cells have flown from beside the company into the brain, 0 to 1, after `e` seconds. */
export const migration = (d: BrainDemo, e: number): number => ease(clamp((e - d.act3) / MIGRATE, 0, 1));

export function pauseBrain(d: BrainDemo, t: number): void {
  if (d.pausedAt === null) d.pausedAt = t;
}

/** Grows on from where it paused; a real cell that had not yet left for the brain leaves that much later. */
export function resumeBrain(d: BrainDemo, t: number): void {
  if (d.pausedAt === null) return;
  const paused = t - d.pausedAt;
  for (const n of [...d.joined.keys(), ...(d.root ? [d.root] : [])])
    if (n.tween && n.tween.start > d.pausedAt) n.tween.start += paused;
  d.pausedFor += paused;
  d.pausedAt = null;
}

/** Plays the demo again from the company as it stood; the cells set aside stay aside. */
export function replayBrain(s: SceneState, d: BrainDemo, t: number): void {
  d.start = d.instant ? t - d.duration : t;
  d.pausedAt = null;
  d.pausedFor = 0;
  if (d.joined.size) moveIntoBrain(d);
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

/** How far the cells set aside have faded out at `t`: in over VEIL_IN, back with the demo's fade-out. */
export const brainVeil = (d: BrainDemo, t: number): number => Math.min(clamp((t - d.began) / VEIL_IN, 0, 1), brainAlpha(d, t));

/**
 * One frame of the demo: the cells set aside fade, the demo leaves the scene once faded out, and
 * while the user has not zoomed or panned the camera follows the acts: close on the company and
 * the story cells born so far, then pulling back to the whole brain, above the teach bar and
 * beside the changes panel.
 */
export function brainStep(s: SceneState, v: View, t: number): void {
  const d = s.brain;
  if (!d) return;
  d.veil = brainVeil(d, t);
  if (d.ending !== null && t - d.ending >= FADE_OUT) {
    s.brain = null;
    return;
  }
  if (s.userZoomed || s.dragging || s.panning || d.ending !== null) return;
  const e = brainElapsed(d, t);
  const [top, bottom] = v.W > 900 ? CLEAR_WIDE : CLEAR_NARROW;
  const close = storyView(d, v, e);
  let ts = close[0],
    tx = close[1],
    ty = close[2];
  if (e >= d.act3) {
    const q = ease(clamp((e - d.act3) / ZOOM_OUT, 0, 1));
    const z0 = ts,
      zb = brainFitZoom(d, v);
    const [bx0, by0, bx1, by1] = d.box;
    // The zoom moves evenly in scale, so the pull-back neither lurches nor crawls, and the centre
    // moves as the view widens, so the story stays in view while the brain comes into it.
    ts = Math.exp(Math.log(z0) + (Math.log(zb) - Math.log(z0)) * q);
    const w = z0 === zb ? q : (1 / ts - 1 / z0) / (1 / zb - 1 / z0);
    tx += ((bx0 + bx1) / 2 - tx) * w;
    ty += ((by0 + by1) / 2 - ty) * w;
  }
  s.cam.ts = ts;
  s.cam.tx = tx;
  // The middle sits in the middle of the room between the demo bar and the tool row.
  s.cam.ty = ty - (top - bottom) / 2 / ts;
}

/**
 * Zoom and centre that show the company's model where it stood before the demo, or the root and
 * the story cells born after `e` seconds, at their places beside it.
 */
function storyView(d: BrainDemo, v: View, e: number): [number, number, number] {
  const [top, bottom] = v.W > 900 ? CLEAR_WIDE : CLEAR_NARROW;
  if (d.joined.size) {
    let x0 = Infinity,
      y0 = Infinity,
      x1 = -Infinity,
      y1 = -Infinity;
    for (const n of [...d.joined.keys(), ...(d.root ? [d.root] : [])]) {
      const at = d.saved.get(n) ?? n;
      x0 = Math.min(x0, at.x - 120);
      y0 = Math.min(y0, at.y - 90);
      x1 = Math.max(x1, at.x + 120);
      y1 = Math.max(y1, at.y + 100);
    }
    const ts = clamp(Math.min((v.W - panelW(v) - 80) / (x1 - x0), (v.H - top - bottom) / (y1 - y0)), STORY_MIN_ZOOM, 1);
    return [ts, (x0 + x1) / 2, (y0 + y1) / 2];
  }
  const rx = d.rootAt ? d.rootAt.x : (d.box[0] + d.box[2]) / 2;
  const ry = d.rootAt ? d.rootAt.y : (d.box[1] + d.box[3]) / 2;
  let x0 = rx - 120,
    y0 = ry - 120,
    x1 = rx + 120,
    y1 = ry + 120;
  const upTo = e >= d.act3 ? d.stories : Math.min(d.stories, bornBy(d, e));
  for (let i = 0; i < upTo; i++) {
    const p = d.cells[i].story as StoryPlace;
    x0 = Math.min(x0, p.x - 90);
    y0 = Math.min(y0, p.y - 60);
    x1 = Math.max(x1, p.x + 90);
    y1 = Math.max(y1, p.y + 70);
  }
  const ts = clamp(Math.min((v.W - panelW(v) - 80) / (x1 - x0), (v.H - top - bottom) / (y1 - y0)), STORY_MIN_ZOOM, 1);
  return [ts, (x0 + x1) / 2, (y0 + y1) / 2];
}

/** The zoom that shows the whole grown brain in the room the camera leaves free. */
export function brainFitZoom(d: BrainDemo, v: View): number {
  const [x0, y0, x1, y1] = d.box;
  const pad = d.spacing * 2;
  const bw = x1 - x0 + 2 * pad,
    bh = y1 - y0 + 2 * pad;
  const [top, bottom] = v.W > 900 ? CLEAR_WIDE : CLEAR_NARROW;
  return clamp(Math.min((v.W - panelW(v) - 80) / bw, (v.H - top - bottom) / bh), BRAIN_MIN_ZOOM, 1);
}
