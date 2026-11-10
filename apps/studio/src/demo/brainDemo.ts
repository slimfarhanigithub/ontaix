/**
 * The demo brain: a large example ontology that grows on the canvas into the shape of a brain,
 * in three acts. It is drawn only: nothing goes to the API, nothing is saved, and a reload or
 * Stop brings the real model back where it was.
 *
 * Nothing grows on its own: example data sources feed every new cell. Each cell buds the moment
 * a pulse of information from the source nearest it reaches the place it buds from.
 *
 * A company that already holds concepts is the brain's starting point: its model stands as it
 * is, close up; then the sources light up under the model one after another and map to its
 * concepts, and new concepts bud from its concepts, each fed by a source and mapped to it; then
 * the root moves to the top of the brain stem, every concept joins the lobe of its domain, the
 * new concepts fly to their lobes and the sources to their places around the brain while the
 * camera pulls back, and the brain grows on from them while more sources join. A company with no
 * concept yet stands alone at the top of the brain stem, close up; the sources light up under it,
 * then three domains bud from its root one after another, each with a few named concepts, their
 * relations drawn one by one and a few relations across the domains, while the camera stays close
 * enough to read every name; then the camera pulls back and the story cells fly to the cores of
 * their lobes. Either way the rest of the brain grows fast, faster and faster, every domain filling one lobe of a side view of a
 * brain whose faint outline shows from the start of the pull-back. As the last pulses land, a
 * wave of light runs through the brain from the top of the stem and leaves it glowing; then it
 * holds still. Cells of other companies fade out and stay set aside until Stop.
 */
import { CELL, C, DOMAIN_TEMPLATES, REDUCED } from '../canvas/constants';
import { clamp, ease } from '../canvas/colour';
import type { SceneState } from '../canvas/state';
import type { Company, Node } from '../canvas/types';
import { panelW, type View } from '../canvas/view';
import { brainPoints, growthOrder, LOBE_CENTRES, lobesOf, neighboursOf, seeded, STEM_TOP, type BrainPoint } from './brainShape';
import { CORE_KEY, namesFor, SOURCE_KEY, SOURCES } from './brainVocabulary';

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
  /** Index of the story cell it buds from, or -1 for the company's root or a real concept. */
  parent: number;
  /** True for a domain, false for one of its concepts. */
  hub: boolean;
  /** The company's own concept it buds from, or null. */
  from: Node | null;
  /** True for an example data source: it maps to concepts beside the company and has no place in the brain. */
  source: boolean;
}

/** A source's mapping to a concept: the source cell, the concept (a story cell's index or a real concept), and when it is drawn. */
export interface BrainBind {
  source: number;
  to: number | Node;
  at: number;
}

/** A pulse of information from a source to a brain cell: the source cell, the brain cell, and when it leaves the source. */
export interface BrainFeed {
  source: number;
  to: number;
  at: number;
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
  /** Mappings from the example sources to concepts, in the order they are drawn. */
  binds: BrainBind[];
  /** Pulses from the sources to the brain cells they feed, in the order they leave. */
  feeds: BrainFeed[];
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
  /** What the camera shows once pulled back: the brain and the row of sources under it. */
  frame: [number, number, number, number];
  start: number;
  /** When the demo was turned on: the other real cells fade out from then. */
  began: number;
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
/**
 * Building on a model: how many of its concepts new ones bud from, how many new concepts bud in
 * all (fewer on a phone), at most per concept, their distance from it, and seconds between them.
 */
const BUD_PARENTS = 6;
const BUD_PARENTS_SMALL = 4;
const BUD_TOTAL = 12;
const BUD_TOTAL_SMALL = 8;
const BUD_MAX = 4;
const BUD_R = 140;
const BUD_R_SMALL = 115;
const BUD_GAP = 0.34;
/** Where a name stands under its cell, in world units: half its width and its drop below the cell's centre. */
const NAME_HALF = 45;
const NAME_DROP = 30;
/**
 * Example data sources: how many (fewer on a phone), their row's distance under the model and
 * least distance between them, their radius (a canvas source's), seconds before a source's first
 * mapping, between its mappings and after its last, and mappings per source at most.
 */
const SOURCE_COUNT = 4;
const SOURCE_COUNT_SMALL = 3;
const SOURCE_DROP = 200;
const SOURCE_STEP = 190;
const SOURCE_R = 16;
const SOURCE_LEAD = 0.35;
const BIND_GAP = 0.12;
const SOURCE_TAIL = 0.25;
const BINDS_MAX = 6;
/**
 * Feeding the brain: sources in all (fewer on a phone); how far under the brain's outline they
 * stand (further on a phone, where a source is larger beside the brain), how much lower every second one stands so long names never meet, the half-width of the
 * strip of cells that outline is read from, and the room the camera keeps beside and under each,
 * in neighbour distances; the share of the brain's width kept free at each end of their row; when the sources that join in the third act appear, as shares of the
 * growth time; and how long a pulse takes from its source to its cell.
 */
const SOURCE_TOTAL = 8;
const SOURCE_TOTAL_SMALL = 4;
const SOURCE_GAP = 4;
const SOURCE_GAP_SMALL = 7;
const SOURCE_STAGGER = 3;
const SOURCE_BAND = 4;
const SOURCE_SIDE_ROOM = 5;
const SOURCE_ROOM = 4;
const SOURCE_INSET = 0.04;
const SOURCE_JOIN = 0.7;
export const FEED_TRAVEL = 0.9;
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
/** World room the close-up camera keeps beside and under a source, for its name. */
const SOURCE_ROOM_CLOSE: [number, number] = [120, 130];

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
  const places = joinPlaces(pts, lobes, taken, spacing * JOIN_GAP);
  for (const n of own.slice().sort((a, b) => a.born - b.born || a.id - b.id)) {
    const lobe = n.domain ? domains.findIndex((x) => x.key === n.domain?.key) : -1;
    if (n.domain && lobe < 0) {
      aside.add(n);
      continue;
    }
    const [ux, uy] = lobe >= 0 ? coreOf(lobe) : STEM_TOP;
    const i = places.take(lobe, ux, uy);
    if (i < 0) {
      aside.add(n);
      continue;
    }
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
  // Story times count from when the sources have connected; they are set once that is known.
  let clock = 0;
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
      story: { x: hx, y: hy, r: STORY_HUB, parent: -1, hub: true, from: null, source: false },
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
        story: { x: hx + Math.cos(a) * conceptR, y: hy + Math.sin(a) * conceptR * tall, r: STORY_CONCEPT, parent: hub, hub: false, from: null, source: false },
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

  // Second act on a model: new concepts bud from the company's own, close up, one after another.
  const model = [...joined.keys()];
  if (joined.size) {
    const k = Math.min(model.length, o.small ? BUD_PARENTS_SMALL : BUD_PARENTS);
    const parents = Array.from({ length: k }, (_, i) => model[Math.floor((i * model.length) / k)]);
    const per = clamp(Math.ceil((o.small ? BUD_TOTAL_SMALL : BUD_TOTAL) / k), 1, BUD_MAX);
    const occupied: [number, number][] = [...model, ...(root ? [root] : [])].map((n) => [n.x, n.y]);
    const mid: [number, number] = [
      occupied.reduce((a, p) => a + p[0], 0) / occupied.length,
      occupied.reduce((a, p) => a + p[1], 0) / occupied.length,
    ];
    // A name stands under its cell: its two ends count as taken too, so no new concept lands on a name.
    const named = (x: number, y: number): [number, number][] => [
      [x - NAME_HALF, y + NAME_DROP],
      [x + NAME_HALF, y + NAME_DROP],
    ];
    for (const n of [...model, ...(root ? [root] : [])]) occupied.push(...named(n.x, n.y));
    const realNames = new Set(model.map((n) => n.label));
    const freshName = (key: string, label: string) => {
      let name = nameOf(key, label);
      for (let i = 0; i < 40 && realNames.has(name); i++) name = nameOf(key, label);
      return name;
    };
    const last = new Map<Node, number>();
    for (let round = 0; round < per; round++)
      for (const p of parents) {
        const lobe = p.domain ? domains.findIndex((x) => x.key === p.domain?.key) : -1;
        const d = lobe >= 0 ? domains[lobe] : null;
        const [sx, sy] = budPlace([p.x, p.y], mid, occupied, o.small ? BUD_R_SMALL : BUD_R);
        occupied.push([sx, sy], ...named(sx, sy));
        const point = nearestFree(...(lobe >= 0 ? coreOf(lobe) : STEM_TOP), (j) => lobes[j] === lobe);
        const [gx, gy] = point >= 0 ? world(pts[point]) : [sx, sy];
        const idx = cells.length;
        if (point >= 0) pointOf.set(point, idx);
        cells.push({
          x: gx,
          y: gy,
          px: p.x,
          py: p.y,
          linked: true,
          color: d ? d.color : C.root,
          domain: d ? d.key : CORE_KEY,
          label: freshName(d ? d.key : CORE_KEY, d ? d.name : 'Company'),
          born: clock,
          story: { x: sx, y: sy, r: STORY_CONCEPT, parent: -1, hub: false, from: p, source: false },
        });
        // Every second concept budding from the same concept is related to its elder sibling.
        const before = last.get(p);
        if (round % 2 === 1 && before !== undefined) links.push([before, idx, clock + 0.35]);
        last.set(p, idx);
        clock += BUD_GAP;
      }
  }

  // Before any of it, the sources light up in a row under the model or the story, one after
  // another, and each maps to the company's concepts nearest it. Then every story cell buds as a
  // pulse from the source nearest it arrives, and a new concept is mapped to that source.
  const binds: BrainBind[] = [];
  const feeds: BrainFeed[] = [];
  const planned = cells.length;
  const first: number[] = [];
  if (planned) {
    const occupied: [number, number][] = [
      ...[...model, ...(root ? [root] : [])].map((n): [number, number] => [n.x, n.y]),
      ...cells.map((c): [number, number] => [(c.story as StoryPlace).x, (c.story as StoryPlace).y]),
    ];
    const xs0 = Math.min(...occupied.map((p) => p[0])),
      xs1 = Math.max(...occupied.map((p) => p[0])),
      ys1 = Math.max(...occupied.map((p) => p[1]));
    const count = Math.min(o.small ? SOURCE_COUNT_SMALL : SOURCE_COUNT, SOURCES.length);
    const step = Math.max(SOURCE_STEP, (xs1 - xs0) / Math.max(1, count - 1));
    const spots = Array.from({ length: count }, (_, i): [number, number] => [(xs0 + xs1) / 2 + (i - (count - 1) / 2) * step, ys1 + SOURCE_DROP]);
    const nearestSpot = (x: number, y: number) => {
      let best = 0;
      spots.forEach(([sx, sy], i) => {
        if (Math.hypot(x - sx, y - sy) < Math.hypot(x - spots[best][0], y - spots[best][1])) best = i;
      });
      return best;
    };
    const mine = spots.map((): Node[] => []);
    for (const n of model) mine[nearestSpot(n.x, n.y)].push(n);
    let t = ACT_ONE;
    spots.forEach(([x, y], i) => {
      const src = cells.length;
      first.push(src);
      cells.push({
        x,
        y,
        px: x,
        py: y,
        linked: false,
        color: s.BRASS,
        domain: SOURCE_KEY,
        label: SOURCES[i],
        born: t,
        story: { x, y, r: SOURCE_R, parent: -1, hub: false, from: null, source: true },
      });
      t += SOURCE_LEAD;
      const nearest = mine[i].sort((a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y)).slice(0, BINDS_MAX);
      for (const n of nearest) {
        binds.push({ source: src, to: n, at: t });
        t += BIND_GAP;
      }
      t += SOURCE_TAIL;
    });
    const start = t + LINK_DRAW + FEED_TRAVEL;
    for (let i = 0; i < planned; i++) {
      const c = cells[i];
      const p = c.story as StoryPlace;
      c.born += start;
      const src = first[nearestSpot(p.x, p.y)];
      feeds.push({ source: src, to: i, at: c.born - FEED_TRAVEL });
      if (!p.hub) binds.push({ source: src, to: i, at: c.born });
    }
    for (const l of links) l[2] += start;
  }
  const stories = cells.length;
  const settledAt = Math.max(...cells.map((c) => c.born), ...links.map((l) => l[2]));
  const act3 = stories ? settledAt + LINK_DRAW + HOLD : ACT_ONE;

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
  for (const c of [...cells.filter((x) => !x.story?.source), ...joined.values()]) {
    x0 = Math.min(x0, c.x);
    y0 = Math.min(y0, c.y);
    x1 = Math.max(x1, c.x);
    y1 = Math.max(y1, c.y);
  }

  // More sources join as the brain grows; all of them stand across its width, each just under
  // the brain's outline where it stands, the first ones spread among the rest, and every brain cell buds as a pulse from the source
  // nearest it, among those shown by then, reaches the place it buds from.
  const frame: [number, number, number, number] = [x0, y0, x1, y1];
  if (first.length) {
    const count = Math.max(first.length, Math.min(o.small ? SOURCE_TOTAL_SMALL : SOURCE_TOTAL, SOURCES.length));
    const all = [...first];
    for (let k = first.length; k < count; k++) {
      all.push(cells.length);
      cells.push({
        x: 0,
        y: 0,
        px: 0,
        py: 0,
        linked: false,
        color: s.BRASS,
        domain: SOURCE_KEY,
        label: SOURCES[k],
        born: g0 + GROW * SOURCE_JOIN * ((k - first.length + 1) / (count - first.length + 1)),
        story: { x: 0, y: 0, r: SOURCE_R, parent: -1, hub: false, from: null, source: true },
      });
    }
    const band = SOURCE_BAND * WORLD_SPACING;
    const inBrain = [...cells.filter((c) => !c.story?.source), ...joined.values()];
    const under = (x: number): number => {
      let y = -Infinity;
      for (const c of inBrain) if (Math.abs(c.x - x) < band) y = Math.max(y, c.y);
      return (y === -Infinity ? (y0 + y1) / 2 : y) + (o.small ? SOURCE_GAP_SMALL : SOURCE_GAP) * WORLD_SPACING;
    };
    const left = x0 + (x1 - x0) * SOURCE_INSET,
      right = x1 - (x1 - x0) * SOURCE_INSET;
    const slots = new Map<number, number>();
    first.forEach((i, k) => slots.set(i, first.length > 1 ? Math.round((k * (count - 1)) / (first.length - 1)) : Math.floor((count - 1) / 2)));
    const used = new Set(slots.values());
    let free = 0;
    for (const i of all.slice(first.length)) {
      while (used.has(free)) free++;
      slots.set(i, free);
      used.add(free);
    }
    for (const i of all) {
      const j = slots.get(i) as number;
      const c = cells[i];
      c.x = c.px = count > 1 ? left + ((right - left) * j) / (count - 1) : (left + right) / 2;
      c.y = c.py = under(c.x) + (j % 2) * SOURCE_STAGGER * WORLD_SPACING;
      // A source that joins in the third act appears at its place.
      if (!first.includes(i)) Object.assign(c.story as StoryPlace, { x: c.x, y: c.y });
      frame[0] = Math.min(frame[0], c.x - SOURCE_SIDE_ROOM * WORLD_SPACING);
      frame[2] = Math.max(frame[2], c.x + SOURCE_SIDE_ROOM * WORLD_SPACING);
      frame[3] = Math.max(frame[3], c.y + SOURCE_ROOM * WORLD_SPACING);
    }
    for (let i = stories; i < cells.length; i++) {
      const c = cells[i];
      if (c.story?.source) continue;
      const at = c.born - FEED_TRAVEL;
      let src = -1,
        bd = Infinity;
      for (const j of all) {
        if (cells[j].born > at) continue;
        const dd = Math.hypot(cells[j].x - c.px, cells[j].y - c.py);
        if (dd < bd) {
          bd = dd;
          src = j;
        }
      }
      if (src >= 0) feeds.push({ source: src, to: i, at });
    }
  }
  inBirthOrder(cells, links, binds, feeds);

  const duration = Math.max(act3 + (joined.size ? JOIN : MIGRATE), total ? g0 + GROW : act3);
  const instant = !!o.instant;
  const demo: BrainDemo = {
    cells,
    stories,
    lobes: domains.length,
    storyDomains: story.length,
    links,
    binds,
    feeds,
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
    frame,
    start: instant ? t - duration : t,
    began: instant ? t - VEIL_IN : t,
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

/**
 * Puts the cells in the order they are born, as `bornBy` needs: a source lights up before the
 * story it feeds, and one that joins in the third act among the brain cells budding then. Every
 * index into the cells follows, and each relation keeps its earlier cell first.
 */
function inBirthOrder(cells: BrainCell[], links: BrainLink[], binds: BrainBind[], feeds: BrainFeed[]): void {
  const order = cells.map((_, i) => i).sort((a, b) => cells[a].born - cells[b].born || a - b);
  const moved = new Array<number>(cells.length);
  order.forEach((old, i) => (moved[old] = i));
  const sorted = order.map((i) => cells[i]);
  cells.splice(0, cells.length, ...sorted);
  for (const c of cells) if (c.story && c.story.parent >= 0) c.story.parent = moved[c.story.parent];
  for (const l of links) {
    const a = moved[l[0]],
      b = moved[l[1]];
    l[0] = Math.min(a, b);
    l[1] = Math.max(a, b);
  }
  for (const b of binds) {
    b.source = moved[b.source];
    if (typeof b.to === 'number') b.to = moved[b.to];
  }
  for (const f of feeds) {
    f.source = moved[f.source];
    f.to = moved[f.to];
  }
}

/**
 * Where a new concept stands beside the concept at `p`, `r` away: the direction around it that
 * keeps farthest from every place in `occupied`, leaning away from the model's middle `mid`.
 */
export function budPlace(p: [number, number], mid: [number, number], occupied: [number, number][], r: number): [number, number] {
  const out = Math.hypot(p[0] - mid[0], p[1] - mid[1]) < 1 ? -Math.PI / 2 : Math.atan2(p[1] - mid[1], p[0] - mid[0]);
  let best: [number, number] = [p[0] + Math.cos(out) * r, p[1] + Math.sin(out) * r],
    score = -Infinity;
  for (let i = 0; i < 24; i++) {
    const turn = Math.ceil(i / 2) * (i % 2 ? 1 : -1);
    const a = out + (turn * Math.PI) / 12;
    const x = p[0] + Math.cos(a) * r,
      y = p[1] + Math.sin(a) * r;
    let room = Infinity;
    for (const [ox, oy] of occupied) room = Math.min(room, Math.hypot(x - ox, y - oy));
    const sc = Math.min(room, r * 1.2) - (Math.abs(turn) * r) / 24;
    if (sc > score) {
      score = sc;
      best = [x, y];
    }
  }
  return best;
}

/**
 * The free points of the brain, lobe by lobe, for the company's concepts to take. `take` gives
 * the point of the lobe nearest its core (the lowest index among equals) that is not taken and
 * stands at least `gap` from every point taken here, or failing that the nearest not taken. A
 * lobe's points are ordered once, nearest first, and scanned once in all: a point passed over
 * for being taken or too close never qualifies again. A grid of the points taken here holds the
 * gap test to the points one cell around.
 */
export function joinPlaces(pts: BrainPoint[], lobes: number[], taken: Set<number>, gap: number): { take(lobe: number, ux: number, uy: number): number } {
  const byLobe = new Map<number, number[]>();
  pts.forEach((_, i) => {
    const list = byLobe.get(lobes[i]);
    if (list) list.push(i);
    else byLobe.set(lobes[i], [i]);
  });
  const ordered = new Map<number, { list: number[]; next: number }>();
  const grid = new Map<string, number[]>();
  const cellOf = (x: number, y: number) => `${Math.floor(x / gap)},${Math.floor(y / gap)}`;
  const apart = (j: number): boolean => {
    const p = pts[j];
    for (let dx = -1; dx <= 1; dx++)
      for (let dy = -1; dy <= 1; dy++) {
        const near = grid.get(cellOf(p.x + dx * gap, p.y + dy * gap));
        if (near) for (const k of near) if (Math.hypot(p.x - pts[k].x, p.y - pts[k].y) < gap) return false;
      }
    return true;
  };
  return {
    take(lobe: number, ux: number, uy: number): number {
      let o = ordered.get(lobe);
      if (!o) {
        const dist = (i: number) => Math.hypot(pts[i].x - ux, pts[i].y - uy);
        o = { list: (byLobe.get(lobe) ?? []).slice().sort((a, b) => dist(a) - dist(b) || a - b), next: 0 };
        ordered.set(lobe, o);
      }
      let i = -1;
      while (o.next < o.list.length) {
        const j = o.list[o.next++];
        if (!taken.has(j) && apart(j)) {
          i = j;
          break;
        }
      }
      if (i < 0) i = o.list.find((j) => !taken.has(j)) ?? -1;
      if (i < 0) return -1;
      taken.add(i);
      const key = cellOf(pts[i].x, pts[i].y);
      const cell = grid.get(key);
      if (cell) cell.push(i);
      else grid.set(key, [i]);
      return i;
    },
  };
}

/** Seconds of the demo so far. */
export const brainElapsed = (d: BrainDemo, t: number): number => t - d.start;

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
    const [bx0, by0, bx1, by1] = d.frame;
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
  let x0 = Infinity,
    y0 = Infinity,
    x1 = -Infinity,
    y1 = -Infinity;
  if (d.joined.size) {
    for (const n of [...d.joined.keys(), ...(d.root ? [d.root] : [])]) {
      const at = d.saved.get(n) ?? n;
      x0 = Math.min(x0, at.x - 120);
      y0 = Math.min(y0, at.y - 90);
      x1 = Math.max(x1, at.x + 120);
      y1 = Math.max(y1, at.y + 100);
    }
  } else {
    const rx = d.rootAt ? d.rootAt.x : (d.box[0] + d.box[2]) / 2;
    const ry = d.rootAt ? d.rootAt.y : (d.box[1] + d.box[3]) / 2;
    x0 = rx - 120;
    y0 = ry - 120;
    x1 = rx + 120;
    y1 = ry + 120;
  }
  const upTo = e >= d.act3 ? d.stories : Math.min(d.stories, bornBy(d, e));
  for (let i = 0; i < upTo; i++) {
    const p = d.cells[i].story as StoryPlace;
    // A source's name is wider and its row the lowest: it gets more room around it.
    const [w, below] = p.source ? SOURCE_ROOM_CLOSE : [90, 70];
    x0 = Math.min(x0, p.x - w);
    y0 = Math.min(y0, p.y - 60);
    x1 = Math.max(x1, p.x + w);
    y1 = Math.max(y1, p.y + below);
  }
  const ts = clamp(Math.min((v.W - panelW(v) - 80) / (x1 - x0), (v.H - top - bottom) / (y1 - y0)), STORY_MIN_ZOOM, 1);
  return [ts, (x0 + x1) / 2, (y0 + y1) / 2];
}

/** The zoom that shows the whole grown brain, and its sources, in the room the camera leaves free. */
export function brainFitZoom(d: BrainDemo, v: View): number {
  const [x0, y0, x1, y1] = d.frame;
  const pad = d.spacing * 2;
  const bw = x1 - x0 + 2 * pad,
    bh = y1 - y0 + 2 * pad;
  const [top, bottom] = v.W > 900 ? CLEAR_WIDE : CLEAR_NARROW;
  return clamp(Math.min((v.W - panelW(v) - 80) / bw, (v.H - top - bottom) / bh), BRAIN_MIN_ZOOM, 1);
}
