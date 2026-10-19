/**
 * Draws the demo brain under the real model: a soft tint per lobe, the relations, the cells and
 * their names.
 *
 * Beside the company, the story cells of the second act are drawn as large as concepts on the
 * canvas, with their names, and their relations reach from one cell to the next as they are
 * made. In the third act they fly into the cores of their lobes and shrink to brain cells.
 *
 * Thousands of cells stay smooth. A cell that has settled never moves again, so from afar
 * settled cells and their relations are painted once into a cached picture of the whole brain,
 * a few more each frame as they settle, and every frame draws that picture in one go plus the
 * cells still budding. Close up, or when the camera is nearer than the picture is sharp, each
 * cell on screen is drawn directly: one copy of a sphere painted once per colour, relations of
 * one colour in one path, and nothing off screen.
 *
 * A cell buds from its parent along its birth link, grows to full size and glows while it is
 * new; with reduced motion it fades in where it belongs, without the glow. From the start of
 * the pull-back a faint ghost of every cell shows the brain the growth is filling. A grown brain
 * holds still.
 */
import { FONT_SANS, MIX_BLACK, MIX_WHITE, themedColour } from '../design/tokens';
import { clamp, ease, hex, mix } from '../canvas/colour';
import { labelScale } from '../canvas/labels';
import { beginLayer, compositeLayer } from '../canvas/regions';
import type { SceneState } from '../canvas/state';
import { toWorld, type View } from '../canvas/view';
import { brainAlpha, brainElapsed, brainFitZoom, bornBy, LINK_DRAW, linksBy, MIGRATE, migration, ZOOM_OUT, type BrainCell, type BrainDemo } from './brainDemo';

/** How long a new cell takes to bud to its place, and how long it glows. */
const BUD = 0.7;
const GLOW = 1.4;
/** How long a cell takes to fade in with reduced motion. */
const FADE_IN_REDUCED = 0.5;
/** Closer than this zoom the brain cells carry their names, at most LABELS_MAX on screen, each only where it overlaps no other. */
const LABEL_ZOOM = 0.55;
const LABELS_MAX = 360;
/** Room kept around a name, in CSS pixels. */
const LABEL_GAP = 6;
/** Smallest on-screen size of a story name, in CSS pixels: a domain's, and a concept's. */
const STORY_HUB_PX = 14;
const STORY_CONCEPT_PX = 12;
/** Pixel radius of the painted sphere each cell is a copy of, and of a glow. */
const SPRITE_R = 32;
/** Opacity of relations, of the story's relations beside the company, and the tint's radius around each cell in neighbour distances. */
const LINK_ALPHA = 0.38;
const STORY_LINK_ALPHA = 0.6;
const TINT_R = 0.85;
/** Opacity of the ghost brain once the camera has pulled back, and its dots' radius in cell radii. */
const GHOST_ALPHA = 0.26;
const GHOST_R = 0.55;
/** Closer than this zoom the ghost brain is not drawn; it is fully drawn 0.25 further out. */
const GHOST_ZOOM = 0.4;
/** Longest side of the cached picture, in pixels: smaller on phones, which have less memory. */
const CACHE_PX_WIDE = 3072;
const CACHE_PX_NARROW = 2048;
/** How much the camera may enlarge the cached picture before cells are drawn directly. */
const CACHE_STRETCH = 1.25;

const sprites = new Map<string, HTMLCanvasElement | null>();
const glowSprites = new Map<string, HTMLCanvasElement | null>();

function paint(size: number, draw: (g: CanvasRenderingContext2D) => void): HTMLCanvasElement | null {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d');
  if (!g) return null;
  g.translate(size / 2, size / 2);
  draw(g);
  return c;
}

/** The matte sphere of a colour, painted as a cell is (`cells.ts`); null without a 2D context. */
function sprite(color: string): HTMLCanvasElement | null {
  if (!sprites.has(color))
    sprites.set(
      color,
      paint(SPRITE_R * 2 + 4, (g) => {
        const col = themedColour(color);
        const r = SPRITE_R;
        const cg = g.createRadialGradient(-r * 0.35, -r * 0.35, r * 0.1, 0, 0, r * 1.04);
        cg.addColorStop(0, hex(mix(col, MIX_WHITE, 0.55), 0.98));
        cg.addColorStop(0.3, hex(mix(col, MIX_WHITE, 0.18), 0.98));
        cg.addColorStop(0.75, hex(col, 0.96));
        cg.addColorStop(1, hex(mix(col, MIX_BLACK, 0.42), 0.96));
        g.fillStyle = cg;
        g.beginPath();
        g.arc(0, 0, r, 0, 6.283);
        g.fill();
        g.strokeStyle = hex(mix(col, MIX_WHITE, 0.35), 0.35);
        g.lineWidth = 2;
        g.stroke();
      }),
    );
  return sprites.get(color) ?? null;
}

/** The soft halo of a new cell. */
function glowSprite(color: string): HTMLCanvasElement | null {
  if (!glowSprites.has(color))
    glowSprites.set(
      color,
      paint(SPRITE_R * 2, (g) => {
        const col = themedColour(color);
        const gr = g.createRadialGradient(0, 0, SPRITE_R * 0.2, 0, 0, SPRITE_R);
        gr.addColorStop(0, hex(mix(col, MIX_WHITE, 0.3), 0.55));
        gr.addColorStop(1, hex(col, 0));
        g.fillStyle = gr;
        g.fillRect(-SPRITE_R, -SPRITE_R, SPRITE_R * 2, SPRITE_R * 2);
      }),
    );
  return glowSprites.get(color) ?? null;
}

/** Draws a cell's sphere centred on x, y with radius r, or a flat disc without sprites. */
function drawSphere(g: CanvasRenderingContext2D, color: string, x: number, y: number, r: number): void {
  const img = sprite(color);
  if (img) {
    const R = r * (1 + 2 / SPRITE_R);
    g.drawImage(img, x - R, y - R, R * 2, R * 2);
    return;
  }
  g.fillStyle = themedColour(color);
  g.beginPath();
  g.arc(x, y, r, 0, 6.283);
  g.fill();
}

/** The world rectangle on screen, grown by `m`. */
function viewRect(s: SceneState, v: View, m: number): [number, number, number, number] {
  const [x0, y0] = toWorld(v, s.cam, 0, 0);
  const [x1, y1] = toWorld(v, s.cam, v.W, v.H);
  return [x0 - m, y0 - m, x1 + m, y1 + m];
}

/**
 * Where a cell rests after `e` seconds and its full radius: a story cell beside the company,
 * then on its way into the brain; any other cell in the brain.
 */
function restOf(d: BrainDemo, c: BrainCell, e: number): [number, number, number] {
  const p = c.story;
  if (!p) return [c.x, c.y, d.radius];
  const m = d.reduced ? (migration(d, e) < 0.5 ? 0 : 1) : migration(d, e);
  return [p.x + (c.x - p.x) * m, p.y + (c.y - p.y) * m, p.r + (d.radius - p.r) * m];
}

/** Where a cell buds from after `e` seconds: its parent's resting place, the root's place, or null for a seed. */
function budOf(d: BrainDemo, c: BrainCell, e: number): [number, number] | null {
  if (!c.linked) return null;
  const p = c.story;
  if (!p) return [c.px, c.py];
  if (p.parent >= 0) {
    const [x, y] = restOf(d, d.cells[p.parent], e);
    return [x, y];
  }
  return d.root ? [d.root.x, d.root.y] : null;
}

/** Where a cell is after `e` seconds and its radius: on its way from its parent while budding, then at rest. */
function at(d: BrainDemo, c: BrainCell, e: number): [number, number, number] {
  const [x, y, r] = restOf(d, c, e);
  if (d.reduced) return [x, y, r];
  const q = ease(clamp((e - c.born) / BUD, 0, 1));
  const from = budOf(d, c, e);
  if (!from) return [x, y, r * (0.45 + 0.55 * q)];
  return [from[0] + (x - from[0]) * q, from[1] + (y - from[1]) * q, r * (0.45 + 0.55 * q)];
}

/** A cell's opacity at age `a`; with reduced motion a story cell also dips while it moves into the brain. */
function cellAlpha(d: BrainDemo, c: BrainCell, e: number): number {
  const a = clamp((e - c.born) / (d.reduced ? FADE_IN_REDUCED : 0.25), 0, 1);
  if (!d.reduced || !c.story) return a;
  return a * Math.abs(1 - 2 * migration(d, e));
}

/**
 * True for the story relations that only belong beside the company: a domain's birth link to the
 * root and a relation across two domains. They would cross the whole brain, so they fade out as
 * the story cells fly into it.
 */
const besideOnly = (a: BrainCell, b?: BrainCell): boolean =>
  b ? !!a.story && !!b.story && a.domain !== b.domain : !!a.story && a.story.parent < 0;

/** Domain keys whose domain is hidden in every company: their lobes are not drawn. */
function hiddenKeys(s: SceneState): Set<string> {
  const shownKeys = new Set(s.DOMAINS.filter((d) => !d.hidden).map((d) => d.key));
  return new Set(s.DOMAINS.filter((d) => d.hidden && !shownKeys.has(d.key)).map((d) => d.key));
}

/** The cached picture of a demo's settled cells, relations and tint. */
interface Cache {
  /** The growth it was painted for (`BrainDemo.start`) and the hidden domains then. */
  start: number;
  hidden: string;
  /** World rectangle it covers, and pixels per world unit. */
  x0: number;
  y0: number;
  w: number;
  h: number;
  scale: number;
  cells: CanvasRenderingContext2D;
  tint: CanvasRenderingContext2D;
  /** Every cell as a faint dot, painted once. */
  ghost: CanvasRenderingContext2D;
  /** Cells and further relations painted so far. */
  upTo: number;
  linksUpTo: number;
  /** Relation width in world units, fit for the view of the whole brain. */
  lineWidth: number;
}

const caches = new WeakMap<BrainDemo, Cache | null>();

function newCache(d: BrainDemo, v: View, hidden: string): Cache | null {
  const [bx0, by0, bx1, by1] = d.box;
  const pad = d.spacing * 2;
  const x0 = bx0 - pad,
    y0 = by0 - pad,
    w = bx1 - bx0 + 2 * pad,
    h = by1 - by0 + 2 * pad;
  const longest = v.W > 900 ? CACHE_PX_WIDE : CACHE_PX_NARROW;
  const scale = Math.min(longest / Math.max(w, h), v.DPR * LABEL_ZOOM);
  const canvas = (k2: number) => {
    const c = document.createElement('canvas');
    c.width = Math.max(1, Math.ceil(w * scale * k2));
    c.height = Math.max(1, Math.ceil(h * scale * k2));
    const g = c.getContext('2d');
    g?.setTransform(scale * k2, 0, 0, scale * k2, -x0 * scale * k2, -y0 * scale * k2);
    return g;
  };
  const cells = canvas(1),
    tint = canvas(0.5),
    ghost = canvas(0.5);
  if (!cells || !tint || !ghost) return null;
  const hiddenKeys = new Set(hidden.split(','));
  for (const c of d.cells) {
    if (hiddenKeys.has(c.domain)) continue;
    ghost.fillStyle = themedColour(c.color);
    ghost.beginPath();
    ghost.arc(c.x, c.y, d.radius * GHOST_R, 0, 6.283);
    ghost.fill();
  }
  return {
    start: d.start,
    hidden,
    x0,
    y0,
    w,
    h,
    scale,
    cells,
    tint,
    ghost,
    upTo: 0,
    linksUpTo: 0,
    lineWidth: Math.max(1.2, 0.9 / brainFitZoom(d, v)),
  };
}

/** How many cells have settled after `e` seconds: none until the story cells have reached the brain. */
const settledBy = (d: BrainDemo, e: number): number => (e < d.act3 + MIGRATE ? 0 : bornBy(d, e - (d.reduced ? FADE_IN_REDUCED : GLOW)));

/** The demo's cache, painted up to the cells settled by now; null without a 2D context. */
function cacheFor(d: BrainDemo, v: View, e: number, hidden: Set<string>): Cache | null {
  const sig = [...hidden].sort().join(',');
  let c = caches.get(d);
  if (c === undefined || (c && (c.start !== d.start || c.hidden !== sig))) {
    c = d.cells.length ? newCache(d, v, sig) : null;
    caches.set(d, c);
  }
  if (!c) return null;
  const settled = settledBy(d, e);
  if (settled <= c.upTo) return c;
  const g = c.cells;
  const r = d.spacing * TINT_R;
  // Relations go under what is painted already.
  const lines = new Map<string, Path2D>();
  const line = (ax: number, ay: number, bx: number, by: number, color: string) => {
    let p = lines.get(color);
    if (!p) lines.set(color, (p = new Path2D()));
    p.moveTo(ax, ay);
    p.lineTo(bx, by);
  };
  for (let i = c.upTo; i < settled; i++) {
    const cell = d.cells[i];
    const from = budOf(d, cell, e);
    if (from && !hidden.has(cell.domain) && !besideOnly(cell)) line(from[0], from[1], cell.x, cell.y, cell.color);
  }
  while (c.linksUpTo < d.links.length && d.links[c.linksUpTo][1] < settled && d.links[c.linksUpTo][2] + LINK_DRAW <= e) {
    const [a, b] = d.links[c.linksUpTo++];
    const ca = d.cells[a],
      cb = d.cells[b];
    if (!hidden.has(ca.domain) && !hidden.has(cb.domain) && !besideOnly(ca, cb)) line(ca.x, ca.y, cb.x, cb.y, cb.color);
  }
  g.globalCompositeOperation = 'destination-over';
  g.lineCap = 'round';
  g.lineWidth = c.lineWidth;
  for (const [color, p] of lines) {
    g.strokeStyle = hex(themedColour(color), LINK_ALPHA);
    g.stroke(p);
  }
  g.globalCompositeOperation = 'source-over';
  for (let i = c.upTo; i < settled; i++) {
    const cell = d.cells[i];
    if (hidden.has(cell.domain)) continue;
    drawSphere(g, cell.color, cell.x, cell.y, d.radius);
    c.tint.fillStyle = themedColour(cell.color);
    c.tint.beginPath();
    c.tint.arc(cell.x, cell.y, r, 0, 6.283);
    c.tint.fill();
  }
  c.upTo = settled;
  return c;
}

/** True when the cached picture is sharp enough for the camera and no names are drawn. */
const cacheServes = (c: Cache | null, s: SceneState, v: View): c is Cache =>
  !!c && s.cam.s < LABEL_ZOOM && s.cam.s * v.DPR <= c.scale * CACHE_STRETCH;

/** Draws a cached layer over its world rectangle. */
function drawCached(ctx: CanvasRenderingContext2D, c: Cache, g: CanvasRenderingContext2D, alpha: number): void {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(g.canvas, c.x0, c.y0, c.w, c.h);
  ctx.restore();
}

/** Close up the tint thins out, so the cells read over it. */
const tintAlpha = (s: SceneState, v: View, d: BrainDemo, t: number): number => v.TH.domA * brainAlpha(d, t) * clamp(1.4 - s.cam.s, 0.4, 1);

/** The lobe tint, drawn in place of the company and domain regions while the demo is on. */
export function drawBrainTint(s: SceneState, v: View, t: number): void {
  const d = s.brain;
  if (!d) return;
  const e = brainElapsed(d, t);
  const n = bornBy(d, e);
  if (!n) return;
  const hidden = hiddenKeys(s);
  const cache = cacheFor(d, v, e, hidden);
  // The ghost shows as the camera pulls back, never close up, where its dots would read as cells.
  const ghost = GHOST_ALPHA * brainAlpha(d, t) * clamp((e - d.act3) / ZOOM_OUT, 0, 1) * clamp((GHOST_ZOOM - s.cam.s) / 0.25, 0, 1);
  if (cache && ghost > 0) drawCached(v.ctx, cache, cache.ghost, ghost);
  if (cacheServes(cache, s, v)) {
    drawCached(v.ctx, cache, cache.tint, tintAlpha(s, v, d, t));
    return;
  }
  // Beside the company the story has no lobes yet; they tint in as the story cells fly into the brain.
  const m = migration(d, e);
  if (n <= d.stories && m < 0.5) return;
  if (!beginLayer(v)) return;
  const [x0, y0, x1, y1] = viewRect(s, v, d.spacing * 2);
  const byColour = new Map<string, Path2D>();
  const r = d.spacing * TINT_R;
  for (let i = m < 0.5 ? d.stories : 0; i < n; i++) {
    const c = d.cells[i];
    const [x, y] = restOf(d, c, e);
    if (hidden.has(c.domain) || x < x0 || x > x1 || y < y0 || y > y1) continue;
    if (e - c.born < BUD * 0.5) continue;
    let p = byColour.get(c.color);
    if (!p) byColour.set(c.color, (p = new Path2D()));
    p.moveTo(x + r, y);
    p.arc(x, y, r, 0, 6.283);
  }
  for (const [color, p] of byColour) {
    v.octx.fillStyle = themedColour(color);
    v.octx.fill(p);
  }
  compositeLayer(v, tintAlpha(s, v, d, t), true);
}

/** The demo's relations, cells and names. */
export function drawBrain(s: SceneState, v: View, t: number): void {
  const d = s.brain;
  if (!d) return;
  const { ctx, TH } = v;
  const e = brainElapsed(d, t);
  const n = bornBy(d, e);
  const fade = brainAlpha(d, t);
  if (!n || fade <= 0) return;
  const hidden = hiddenKeys(s);
  const cache = cacheFor(d, v, e, hidden);
  const cached = cacheServes(cache, s, v);
  // From afar the cached picture holds the settled cells; only the newer ones are drawn here.
  const from = cached ? cache.upTo : 0;
  if (cached) drawCached(ctx, cache, cache.cells, fade);
  const [x0, y0, x1, y1] = viewRect(s, v, d.spacing * 2);
  const inRect = (x: number, y: number) => x >= x0 && x <= x1 && y >= y0 && y <= y1;
  const zoom = s.cam.s;
  const width = cached ? cache.lineWidth : Math.max(1.2, 0.9 / zoom);
  const m = migration(d, e);
  // Story relations are drawn as strongly as the canvas's own, fading to the brain's as they fly in.
  const storyAlpha = STORY_LINK_ALPHA + (LINK_ALPHA - STORY_LINK_ALPHA) * m;
  const storyWidth = Math.max(width, 2 + (width - 2) * m);
  const places = new Map<number, [number, number, number]>();
  const placeOf = (i: number) => {
    let p = places.get(i);
    if (!p) places.set(i, (p = at(d, d.cells[i], e)));
    return p;
  };

  // Relations: settled ones as one path per colour, growing and story ones one by one.
  const settled = new Map<string, Path2D>();
  const line = (ax: number, ay: number, bx: number, by: number, color: string) => {
    let p = settled.get(color);
    if (!p) settled.set(color, (p = new Path2D()));
    p.moveTo(ax, ay);
    p.lineTo(bx, by);
  };
  const stroke = (ax: number, ay: number, bx: number, by: number, color: string, alpha: number, w: number) => {
    ctx.strokeStyle = hex(themedColour(color), alpha * fade);
    ctx.lineWidth = w;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(bx, by);
    ctx.stroke();
  };
  ctx.lineCap = 'round';
  for (let i = from; i < n; i++) {
    const c = d.cells[i];
    if (hidden.has(c.domain)) continue;
    const bud = budOf(d, c, e);
    if (!bud) continue;
    const [x, y] = placeOf(i);
    if (!inRect(x, y) && !inRect(bud[0], bud[1])) continue;
    const a = e - c.born;
    if (c.story) stroke(bud[0], bud[1], x, y, c.color, storyAlpha * clamp(a / 0.2, 0, 1) * (besideOnly(c) ? 1 - m : 1), storyWidth);
    else if (a >= BUD || d.reduced) line(bud[0], bud[1], x, y, c.color);
    else stroke(bud[0], bud[1], x, y, c.color, 0.5 * clamp(a / 0.2, 0, 1), width);
  }
  const drawn = linksBy(d, e);
  for (let k = cached ? cache.linksUpTo : 0; k < drawn; k++) {
    const [a, b, when] = d.links[k];
    const ca = d.cells[a],
      cb = d.cells[b];
    if (hidden.has(cb.domain) || hidden.has(ca.domain)) continue;
    const [ax, ay] = placeOf(a),
      [bx, by] = placeOf(b);
    if (!inRect(ax, ay) && !inRect(bx, by)) continue;
    if (b < d.stories) {
      // A story relation reaches from its first cell to its second.
      const q = d.reduced ? 1 : ease(clamp((e - when) / LINK_DRAW, 0, 1));
      const k = (d.reduced ? clamp((e - when) / LINK_DRAW, 0, 1) : 1) * (besideOnly(ca, cb) ? 1 - m : 1);
      if (k > 0) stroke(ax, ay, ax + (bx - ax) * q, ay + (by - ay) * q, cb.color, storyAlpha * k, storyWidth);
    } else if (e - cb.born >= BUD || d.reduced) line(ax, ay, bx, by, cb.color);
  }
  ctx.lineWidth = width;
  for (const [color, p] of settled) {
    ctx.strokeStyle = hex(themedColour(color), LINK_ALPHA * fade);
    ctx.stroke(p);
  }

  // Glows: new cells while they bud.
  if (!d.reduced) {
    for (let i = n - 1; i >= 0; i--) {
      const c = d.cells[i];
      const a = e - c.born;
      if (a >= GLOW) break;
      if (hidden.has(c.domain)) continue;
      const [x, y, r] = placeOf(i);
      if (!inRect(x, y)) continue;
      const img = glowSprite(c.color);
      if (!img) continue;
      const R = r * 2.8;
      ctx.globalAlpha = (1 - a / GLOW) * fade;
      ctx.drawImage(img, x - R, y - R, R * 2, R * 2);
    }
    ctx.globalAlpha = 1;
  }

  // Cells.
  const shownCells: [BrainCell, number, number, number, number][] = [];
  const storyCells: [BrainCell, number, number, number, number][] = [];
  for (let i = from; i < n; i++) {
    const c = d.cells[i];
    if (hidden.has(c.domain)) continue;
    const [x, y, r] = placeOf(i);
    if (!inRect(x, y)) continue;
    const alpha = fade * cellAlpha(d, c, e);
    ctx.globalAlpha = alpha;
    drawSphere(ctx, c.color, x, y, r);
    if (c.story && m < 1) storyCells.push([c, x, y, r, alpha * (1 - m)]);
    else if (shownCells.length <= LABELS_MAX) shownCells.push([c, x, y, r, alpha]);
  }
  ctx.globalAlpha = 1;

  ctx.textAlign = 'center';
  ctx.shadowColor = TH.shadow;
  ctx.shadowBlur = 4;
  // Story names, beside the company: always readable, a domain's a little larger and bolder.
  // Domains are named first, then concepts in the order they were born, each only where it
  // overlaps no name placed already nor the company's own name.
  const taken: [number, number, number, number][] = [];
  if (d.root && storyCells.length) {
    const rr = d.root.r;
    taken.push([d.root.x - 80 / zoom, d.root.y + rr, d.root.x + 80 / zoom, d.root.y + rr + 40 / zoom]);
  }
  storyCells.sort((a, b) => Number(!!b[0].story?.hub) - Number(!!a[0].story?.hub));
  for (const [c, x, y, r, alpha] of storyCells) {
    if (alpha <= 0.01) continue;
    const hub = !!c.story?.hub;
    const size = Math.max((hub ? STORY_HUB_PX : STORY_CONCEPT_PX) / zoom, (hub ? 15 : 13) * labelScale(zoom));
    ctx.font = `${hub ? 600 : 500} ${Math.round(size)}px ${FONT_SANS}`;
    const base = y + r + size * 1.15;
    const half = ctx.measureText(c.label).width / 2 + 3 / zoom;
    const box: [number, number, number, number] = [x - half, base - size, x + half, base + size * 0.3];
    if (!hub && taken.some(([a, b, cc, dd]) => box[0] < cc && box[2] > a && box[1] < dd && box[3] > b)) continue;
    taken.push(box);
    ctx.fillStyle = `rgba(${TH.INK},${0.92 * alpha})`;
    ctx.fillText(c.label, x, base);
  }
  // Brain names, close up: the oldest cells first, each name only where it overlaps none drawn yet.
  if (!cached && zoom >= LABEL_ZOOM && shownCells.length <= LABELS_MAX) {
    const k = labelScale(zoom);
    const size = Math.round(11 * k);
    ctx.font = `500 ${size}px ${FONT_SANS}`;
    const placed: [number, number, number, number][] = [];
    const gap = LABEL_GAP / zoom;
    for (const [c, x, y, r, alpha] of shownCells) {
      const w = ctx.measureText(c.label).width / 2 + gap,
        top = y + r + 15 * k - size - gap,
        bottom = y + r + 15 * k + gap * 0.5;
      if (placed.some(([a, b, cc, dd]) => x - w < cc && x + w > a && top < dd && bottom > b)) continue;
      placed.push([x - w, top, x + w, bottom]);
      ctx.fillStyle = `rgba(${TH.INK},${0.88 * alpha})`;
      ctx.fillText(c.label, x, y + r + 15 * k);
    }
  }
  ctx.shadowBlur = 0;
}
