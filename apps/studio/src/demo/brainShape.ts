/**
 * The shape the demo brain grows into: a side view of a human brain, front to the left, in unit
 * coordinates (about -1 to 1 across, -0.7 to 0.9 down). The cerebrum is folded into gyri by
 * warped concentric bands, the cerebellum into finer parallel bands, and the lateral and central
 * sulci split the cerebrum into lobes; the brain stem rises under it. Points sit on a jittered
 * hexagonal grid inside the folds, so from far away the cells draw the silhouette and its folds.
 *
 * Everything here is pure and draws from its own seeded generator, never from the Studio's shared
 * random stream.
 */

/** Where a point of the brain lies. */
export type BrainPart = 'cerebrum' | 'cerebellum' | 'stem';

export interface BrainPoint {
  /** Unit coordinates. */
  x: number;
  y: number;
  part: BrainPart;
}

/** A small seeded generator (mulberry32): the same seed always draws the same brain. */
export function seeded(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const sq = (v: number): number => v * v;

/** Distance from a point to the segment from a to b. */
function toSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax,
    dy = by - ay;
  const l2 = dx * dx + dy * dy;
  const u = l2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2)) : 0;
  return Math.hypot(px - (ax + dx * u), py - (ay + dy * u));
}

/** Distance from a point to a polyline. */
function toLine(px: number, py: number, line: [number, number][]): number {
  let d = Infinity;
  for (let i = 1; i < line.length; i++) d = Math.min(d, toSegment(px, py, line[i - 1][0], line[i - 1][1], line[i][0], line[i][1]));
  return d;
}

/** The lateral sulcus, between the temporal lobe and the lobes above it. */
const LATERAL: [number, number][] = [
  [-0.5, 0.17],
  [-0.15, 0.11],
  [0.2, 0.06],
  [0.46, -0.06],
];
/** The central sulcus, between the frontal and the parietal lobe. */
const CENTRAL: [number, number][] = [
  [0.02, -0.64],
  [-0.06, -0.38],
  [0.0, -0.14],
  [-0.06, 0.08],
];

const inCerebellum = (x: number, y: number, k = 1): boolean => sq((x - 0.6) / (0.31 * k)) + sq((y - 0.47) / (0.19 * k)) < 1;

function inCerebrum(x: number, y: number): boolean {
  const upper = sq(x / 1.0) + sq((y + 0.02) / 0.64) < 1 && y < 0.24;
  const temporal = sq((x + 0.02) / 0.6) + sq((y - 0.24) / 0.2) < 1;
  const frontal = sq((x + 0.6) / 0.38) + sq((y - 0.1) / 0.3) < 1;
  return (upper || temporal || frontal) && !inCerebellum(x, y, 1.18);
}

const inStem = (x: number, y: number): boolean => toSegment(x, y, 0.29, 0.3, 0.39, 0.86) < 0.052 && !inCerebellum(x, y, 1.12);

/** Smooth pseudo-noise from seeded waves of about `freq` cycles per unit, in about -1 to 1. */
function waves(rand: () => number, count: number, freq: number): (x: number, y: number) => number {
  const w = Array.from({ length: count }, () => {
    const a = rand() * Math.PI * 2,
      f = freq * (0.75 + rand() * 0.5);
    return { fx: Math.cos(a) * f, fy: Math.sin(a) * f, p: rand() * Math.PI * 2 };
  });
  return (x, y) => w.reduce((a, q) => a + Math.sin(q.fx * x + q.fy * y + q.p), 0) / Math.sqrt(count);
}

/** The seeded fields that fold the brain: a slow warp for the cerebellum, a labyrinth for the gyri. */
export interface BrainField {
  warp: (x: number, y: number) => number;
  fold: (x: number, y: number) => number;
}

/** How close to zero the folding field must be for a point to fall in a groove. */
const FOLD_GROOVE = 0.24;

export function brainField(seed: number): BrainField {
  const rand = seeded(seed);
  const warp = waves(rand, 7, 4);
  const coarse = waves(rand, 9, 15);
  const fine = waves(rand, 9, 26);
  return { warp, fold: (x, y) => coarse(x, y) + 0.45 * fine(x + 0.15 * warp(x, y), y) };
}

/**
 * The part a unit point belongs to, or null when it falls outside the brain, in a sulcus or
 * between two gyri.
 */
export function brainPartAt(x: number, y: number, field: BrainField): BrainPart | null {
  if (inStem(x, y)) return 'stem';
  if (inCerebellum(x, y)) {
    // Folia: thin bands bowed like the cerebellum's lower outline, one above the other.
    const v = y - 0.47 + 0.55 * sq(x - 0.6);
    return Math.sin(v * 70 + field.warp(x, y) * 0.6) > -0.4 ? 'cerebellum' : null;
  }
  if (!inCerebrum(x, y)) return null;
  if (toLine(x, y, LATERAL) < 0.03 || toLine(x, y, CENTRAL) < 0.022) return null;
  // Gyri: the grooves are where the folding field crosses zero, which meanders like a labyrinth.
  return Math.abs(field.fold(x, y)) > FOLD_GROOVE ? 'cerebrum' : null;
}

/**
 * The points of a brain with `spacing` between neighbours (unit coordinates), from `seed`.
 * Smaller spacing gives more points: 0.026 gives about 2,600, 0.034 about 1,500.
 */
export function brainPoints(spacing: number, seed = 7): BrainPoint[] {
  const field = brainField(seed);
  const rand = seeded(seed + 1);
  const out: BrainPoint[] = [];
  const rowH = spacing * 0.866;
  let row = 0;
  for (let y = -0.72; y <= 0.92; y += rowH, row++) {
    for (let x = -1.05 + (row % 2 ? spacing / 2 : 0); x <= 1.05; x += spacing) {
      const jx = x + (rand() - 0.5) * spacing * 0.35,
        jy = y + (rand() - 0.5) * spacing * 0.35;
      const part = brainPartAt(jx, jy, field);
      if (part) out.push({ x: jx, y: jy, part });
    }
  }
  return out;
}

/**
 * Anatomical centres the demo's domains spread from, in the order they are handed out: the
 * first few domains take lobes far apart, so even three domains read as three lobes.
 */
export const LOBE_CENTRES: [number, number][] = [
  [-0.72, -0.08], // frontal pole
  [0.38, -0.42], // parietal
  [0.0, 0.27], // temporal
  [0.6, 0.47], // cerebellum
  [0.82, -0.08], // occipital
  [-0.32, -0.46], // upper frontal
  [-0.42, 0.18], // lower frontal
  [0.05, -0.22], // motor strip
  [0.44, 0.12], // back of the temporal lobe
];

/**
 * Splits the points into `count` regions, one per domain: each point joins the nearest centre.
 * Centres beyond the anatomical ones are the points farthest from every centre so far. The stem
 * belongs to no domain (-1): the companies' roots sit there.
 */
export function lobesOf(points: BrainPoint[], count: number): number[] {
  if (count <= 0) return points.map(() => -1);
  const centres = LOBE_CENTRES.slice(0, count);
  while (centres.length < count) {
    let best: [number, number] = [0, 0],
      bd = -1;
    for (const p of points) {
      if (p.part === 'stem') continue;
      const d = Math.min(...centres.map(([cx, cy]) => Math.hypot(p.x - cx, p.y - cy)));
      if (d > bd) {
        bd = d;
        best = [p.x, p.y];
      }
    }
    centres.push(best);
  }
  return points.map((p) => {
    if (p.part === 'stem') return -1;
    let best = 0,
      bd = Infinity;
    centres.forEach(([cx, cy], i) => {
      const d = Math.hypot(p.x - cx, p.y - cy);
      if (d < bd) {
        bd = d;
        best = i;
      }
    });
    return best;
  });
}

/** Indices of the points within `radius` of each point, from a bucket grid. */
export function neighboursOf(points: BrainPoint[], radius: number): number[][] {
  const key = (gx: number, gy: number) => `${gx},${gy}`;
  const grid = new Map<string, number[]>();
  points.forEach((p, i) => {
    const k = key(Math.floor(p.x / radius), Math.floor(p.y / radius));
    const list = grid.get(k);
    if (list) list.push(i);
    else grid.set(k, [i]);
  });
  return points.map((p) => {
    const gx = Math.floor(p.x / radius),
      gy = Math.floor(p.y / radius);
    const near: number[] = [];
    for (let dx = -1; dx <= 1; dx++)
      for (let dy = -1; dy <= 1; dy++)
        for (const j of grid.get(key(gx + dx, gy + dy)) ?? []) {
          const q = points[j];
          if (q !== p && Math.hypot(q.x - p.x, q.y - p.y) <= radius) near.push(j);
        }
    return near;
  });
}

export interface GrowthOrder {
  /** Point indices in the order they are born; seeds first. */
  order: number[];
  /** Parent point of each point (-1 for a seed). */
  parent: number[];
}

/**
 * The order the brain grows in: from the seeds outward, each point born next to one already
 * grown, along neighbour steps of random length, so the front spreads like tissue rather than as
 * a perfect circle. A point no neighbour step reaches (an island between folds) is born from its
 * nearest grown point once everything else is grown.
 */
export function growthOrder(points: BrainPoint[], near: number[][], seeds: number[], seed = 11): GrowthOrder {
  const rand = seeded(seed);
  const parent = points.map(() => -1);
  const dist = points.map(() => Infinity);
  const done = points.map(() => false);
  const order: number[] = [];
  // A binary heap of [distance, point].
  const heap: [number, number][] = [];
  const push = (d: number, i: number) => {
    heap.push([d, i]);
    let c = heap.length - 1;
    while (c > 0) {
      const p = (c - 1) >> 1;
      if (heap[p][0] <= heap[c][0]) break;
      [heap[p], heap[c]] = [heap[c], heap[p]];
      c = p;
    }
  };
  const pop = (): [number, number] => {
    const top = heap[0];
    const last = heap.pop() as [number, number];
    if (heap.length) {
      heap[0] = last;
      let c = 0;
      for (;;) {
        const l = 2 * c + 1,
          r = l + 1;
        let m = c;
        if (l < heap.length && heap[l][0] < heap[m][0]) m = l;
        if (r < heap.length && heap[r][0] < heap[m][0]) m = r;
        if (m === c) break;
        [heap[m], heap[c]] = [heap[c], heap[m]];
        c = m;
      }
    }
    return top;
  };
  for (const s of seeds) {
    if (dist[s] === 0) continue;
    dist[s] = 0;
    push(0, s);
  }
  const grow = () => {
    while (heap.length) {
      const [d, i] = pop();
      if (done[i] || d > dist[i]) continue;
      done[i] = true;
      order.push(i);
      for (const j of near[i]) {
        if (done[j]) continue;
        const step = Math.hypot(points[j].x - points[i].x, points[j].y - points[i].y) * (0.35 + rand() * 1.3);
        if (d + step < dist[j]) {
          dist[j] = d + step;
          parent[j] = i;
          push(dist[j], j);
        }
      }
    }
  };
  grow();
  // Islands: each joins the nearest grown point and grows from there.
  for (let i = 0; i < points.length; i++) {
    if (done[i]) continue;
    let best = -1,
      bd = Infinity;
    for (const j of order) {
      const d = Math.hypot(points[j].x - points[i].x, points[j].y - points[i].y);
      if (d < bd) {
        bd = d;
        best = j;
      }
    }
    parent[i] = best;
    dist[i] = (best >= 0 ? dist[best] : 0) + bd;
    push(dist[i], i);
    grow();
  }
  return { order, parent };
}
