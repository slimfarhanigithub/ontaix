/**
 * The shape the demo brain grows into: a side view of a human brain, front to the left, in unit
 * coordinates (about -1 to 1 across, -0.76 to 0.9 down). The cerebrum's outline follows an
 * anatomical profile; its gyri are the land between the zeros of a folding field whose stripes
 * run the way a real brain's gyri run in each region; the cerebellum is folded into fine bowed
 * folia; the lateral, central and parieto-occipital sulci cut the cerebrum into lobes; the brain
 * stem rises under it. Points sit on a jittered hexagonal grid inside the folds, so from far
 * away the cells draw the silhouette and its folds.
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

/** Points through which a line runs, smoothed by a Catmull-Rom curve with `k` steps a span. */
function smooth(pts: [number, number][], k: number, closed: boolean): [number, number][] {
  const out: [number, number][] = [];
  const n = pts.length;
  const at = (i: number) => (closed ? pts[(i + n) % n] : pts[Math.max(0, Math.min(n - 1, i))]);
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const p0 = at(i - 1),
      p1 = at(i),
      p2 = at(i + 1),
      p3 = at(i + 2);
    for (let j = 0; j < k; j++) {
      const t = j / k,
        t2 = t * t,
        t3 = t2 * t;
      const f = (a: number, b: number, c: number, d: number) => 0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (3 * b - a - 3 * c + d) * t3);
      out.push([f(p0[0], p1[0], p2[0], p3[0]), f(p0[1], p1[1], p2[1], p3[1])]);
    }
  }
  if (!closed) out.push(pts[n - 1]);
  return out;
}

/** True when a point lies inside a closed outline. */
function inside(px: number, py: number, ring: [number, number][]): boolean {
  let c = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i],
      [xj, yj] = ring[j];
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}

/**
 * The cerebrum's outline: the dome from the frontal pole over to the occipital pole, the
 * occipital lobe's underside over the cerebellum, the temporal lobe's lower edge forward to the
 * temporal pole, the notch where the lateral sulcus opens, and the frontal lobe's underside.
 */
const CEREBRUM = smooth(
  [
    [-1.0, -0.02],
    [-0.95, -0.24],
    [-0.84, -0.42],
    [-0.66, -0.57],
    [-0.42, -0.67],
    [-0.14, -0.72],
    [0.14, -0.71],
    [0.42, -0.64],
    [0.66, -0.5],
    [0.85, -0.31],
    [0.97, -0.1],
    [1.01, 0.08],
    [0.96, 0.2],
    [0.82, 0.25],
    [0.62, 0.27],
    [0.42, 0.33],
    [0.2, 0.41],
    [-0.04, 0.44],
    [-0.24, 0.41],
    [-0.38, 0.34],
    [-0.46, 0.25],
    [-0.45, 0.16],
    [-0.52, 0.17],
    [-0.7, 0.18],
    [-0.86, 0.14],
    [-0.96, 0.07],
  ],
  8,
  true,
);
const CEREBRUM_RIM: [number, number][] = [...CEREBRUM, CEREBRUM[0]];
/** The lateral sulcus, between the temporal lobe and the lobes above it. */
const LATERAL = smooth(
  [
    [-0.47, 0.15],
    [-0.3, 0.09],
    [-0.05, 0.04],
    [0.2, -0.02],
    [0.38, -0.12],
    [0.46, -0.2],
  ],
  6,
  false,
);
/** The central sulcus, between the frontal and the parietal lobe. */
const CENTRAL = smooth(
  [
    [0.06, -0.72],
    [0.0, -0.55],
    [0.04, -0.4],
    [-0.04, -0.25],
    [0.0, -0.12],
    [-0.06, 0.02],
  ],
  6,
  false,
);
/** The parieto-occipital sulcus, notching the dome near the back. */
const PARIETO_OCCIPITAL = smooth(
  [
    [0.66, -0.52],
    [0.7, -0.4],
    [0.66, -0.3],
  ],
  6,
  false,
);

/** The cerebellum: an ellipse tilted a little, tucked under the occipital lobe. */
const CEREBELLUM = { x: 0.66, y: 0.44, rx: 0.3, ry: 0.17, tilt: -0.12 };
function cerebellumLocal(x: number, y: number): [number, number] {
  const dx = x - CEREBELLUM.x,
    dy = y - CEREBELLUM.y,
    c = Math.cos(CEREBELLUM.tilt),
    s = Math.sin(CEREBELLUM.tilt);
  return [(dx * c + dy * s) / CEREBELLUM.rx, (-dx * s + dy * c) / CEREBELLUM.ry];
}
const inCerebellum = (x: number, y: number): boolean => {
  const [u, v] = cerebellumLocal(x, y);
  return u * u + v * v < 1;
};

/** The brain stem's axis, from under the temporal lobe down; it is widest at the top. */
const STEM: [number, number, number, number] = [0.36, 0.3, 0.43, 0.84];
/** Where the company's root sits: the top of the brain stem. */
export const STEM_TOP: [number, number] = [0.36, 0.3];
const inStem = (x: number, y: number): boolean => toSegment(x, y, ...STEM) < 0.055 + 0.02 * Math.max(0, Math.min(1, (0.62 - y) / 0.3));

/**
 * Smooth pseudo-noise from seeded waves of about `freq` radians per unit, in about -1 to 1. The
 * waves point within `spread` of `angle`, so a narrow spread gives stripes across that angle.
 */
function waves(rand: () => number, count: number, freq: number, angle = 0, spread = Math.PI): (x: number, y: number) => number {
  const w = Array.from({ length: count }, (_, i) => {
    const a = angle - spread / 2 + ((i + rand()) / count) * spread,
      f = freq * (0.85 + rand() * 0.3);
    return { fx: Math.cos(a) * f, fy: Math.sin(a) * f, p: rand() * Math.PI * 2 };
  });
  return (x, y) => w.reduce((a, q) => a + Math.sin(q.fx * x + q.fy * y + q.p), 0) / Math.sqrt(count / 2);
}

/**
 * Regions where the gyri run one way, as centre, radius, the angle across the gyri and how much
 * it varies: the frontal gyri run front to back, the gyri beside the central sulcus run up and
 * down along it, the temporal gyri run along the lateral sulcus, and the back of the brain winds.
 */
const GRAIN: [number, number, number, number, number][] = [
  [-0.6, -0.25, 0.45, Math.PI / 2 + 0.25, 0.9],
  [-0.62, 0.05, 0.3, Math.PI / 2 - 0.1, 0.9],
  [0.02, -0.38, 0.22, 0.12, 0.7],
  [0.0, 0.28, 0.32, Math.PI / 2 - 0.25, 0.8],
  [0.55, -0.2, 0.4, 0, Math.PI],
];
/** Width of a gyrus in point spacings, and how close to zero the folding field must be for a point to fall in a groove. */
const GYRUS = 5.4;
const GROOVE = 0.24;

/** The seeded fields that fold the brain: a slow warp, and the folding field whose zeros are the grooves. */
export interface BrainField {
  warp: (x: number, y: number) => number;
  fold: (x: number, y: number) => number;
}

/** The folding field for points `spacing` apart, so a gyrus is always about GYRUS points wide. */
export function brainField(seed: number, spacing: number): BrainField {
  const rand = seeded(seed);
  const warp = waves(rand, 7, 4);
  const freq = Math.PI / (GYRUS * spacing);
  const grains = GRAIN.map(([, , , a, spread]) => waves(rand, 12, freq, a, spread));
  const grain = (x: number, y: number) => {
    let sum = 0,
      weights = 0;
    GRAIN.forEach(([cx, cy, r], i) => {
      const w = Math.exp(-(sq(x - cx) + sq(y - cy)) / sq(r));
      sum += w * grains[i](x, y);
      weights += w * w;
    });
    return sum / Math.sqrt(weights + 1e-9);
  };
  return { warp, fold: (x, y) => grain(x + 0.03 * warp(x, y + 1), y + 0.03 * warp(x + 2, y)) };
}

/**
 * The part a unit point belongs to, or null when it falls outside the brain, in a sulcus or
 * between two gyri. The cerebrum's rim stays whole, so the outline reads from afar.
 */
export function brainPartAt(x: number, y: number, field: BrainField, spacing: number): BrainPart | null {
  const cerebrum = inside(x, y, CEREBRUM);
  if (!cerebrum && inStem(x, y) && !inCerebellum(x, y)) return 'stem';
  if (!cerebrum && inCerebellum(x, y)) {
    if (toLine(x, y, CEREBRUM_RIM) < spacing * 1.1) return null;
    // Folia: thin bands bowed like the cerebellum's lower outline, one above the other.
    const [u, v] = cerebellumLocal(x, y);
    const band = (v + 0.45 * u * u) * CEREBELLUM.ry;
    return Math.sin(band * (Math.PI / (1.25 * spacing)) + field.warp(x, y) * 0.4) > -0.45 ? 'cerebellum' : null;
  }
  if (!cerebrum) return null;
  if (toLine(x, y, LATERAL) < spacing || toLine(x, y, CENTRAL) < spacing * 0.8 || toLine(x, y, PARIETO_OCCIPITAL) < spacing * 0.7) return null;
  if (toLine(x, y, CEREBRUM_RIM) < spacing * 0.9) return 'cerebrum';
  return Math.abs(field.fold(x, y)) > GROOVE ? 'cerebrum' : null;
}

/**
 * The points of a brain with `spacing` between neighbours (unit coordinates), from `seed`.
 * Smaller spacing gives more points: 0.022 gives about 3,400, 0.03 about 1,800.
 */
export function brainPoints(spacing: number, seed = 7): BrainPoint[] {
  const field = brainField(seed, spacing);
  const rand = seeded(seed + 1);
  const out: BrainPoint[] = [];
  const rowH = spacing * 0.866;
  let row = 0;
  for (let y = -0.76; y <= 0.92; y += rowH, row++) {
    for (let x = -1.05 + (row % 2 ? spacing / 2 : 0); x <= 1.05; x += spacing) {
      const jx = x + (rand() - 0.5) * spacing * 0.3,
        jy = y + (rand() - 0.5) * spacing * 0.3;
      const part = brainPartAt(jx, jy, field, spacing);
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
  [-0.02, 0.27], // temporal
  [0.66, 0.44], // cerebellum
  [0.8, -0.05], // occipital
  [-0.32, -0.5], // upper frontal
  [-0.55, 0.05], // lower frontal
  [0.0, -0.3], // motor strip
  [0.4, 0.15], // back of the temporal lobe
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
