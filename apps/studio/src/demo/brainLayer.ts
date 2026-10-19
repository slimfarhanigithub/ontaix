/**
 * Draws the demo brain under the real model: a soft tint per lobe, the relations, the cells and,
 * close up, their names.
 *
 * Thousands of cells stay smooth. A cell that has settled never moves again, so from afar
 * settled cells and their relations are painted once into a cached picture of the whole brain,
 * a few more each frame as they settle, and every frame draws that picture in one go plus the
 * cells still budding. Close up, or when the camera is nearer than the picture is sharp, each
 * cell on screen is drawn directly: one copy of a sphere painted once per colour, relations of
 * one colour in one path, and nothing off screen.
 *
 * A cell buds from its parent along its birth link, grows to full size and glows while it is
 * new; with reduced motion it fades in where it belongs, without the glow. Once the brain is
 * grown, cells light up here and there.
 */
import { FONT_SANS, MIX_BLACK, MIX_WHITE, themedColour } from '../design/tokens';
import { clamp, ease, hex, mix } from '../canvas/colour';
import { labelScale } from '../canvas/labels';
import { beginLayer, compositeLayer } from '../canvas/regions';
import type { SceneState } from '../canvas/state';
import { toWorld, type View } from '../canvas/view';
import { brainAlpha, brainElapsed, brainFitZoom, bornBy, type BrainCell, type BrainDemo } from './brainDemo';

/** How long a new cell takes to bud to its place, and how long it glows. */
const BUD = 0.7;
const GLOW = 1.4;
/** How long a cell takes to fade in with reduced motion. */
const FADE_IN_REDUCED = 0.5;
/** Closer than this zoom the cells carry their names, at most LABELS_MAX on screen, each only where it overlaps no other. */
const LABEL_ZOOM = 0.55;
const LABELS_MAX = 360;
/** Room kept around a name, in CSS pixels. */
const LABEL_GAP = 6;
/** Pixel radius of the painted sphere each cell is a copy of, and of a glow. */
const SPRITE_R = 32;
/** Share of a grown brain's cells lit at any moment, and how often each one fires per second. */
const FIRE_SHARE = 0.015;
const FIRE_RATE = 0.35;
/** Opacity of relations, and the tint's radius around each cell in neighbour distances. */
const LINK_ALPHA = 0.38;
const TINT_R = 1.25;
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

/** The soft halo of a new or firing cell. */
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

/** Where a cell is at age `a`, and its size: on its way from its parent while budding, then at its place. */
function at(c: BrainCell, a: number, reduced: boolean): [number, number, number] {
  if (reduced) return [c.x, c.y, 1];
  const q = ease(clamp(a / BUD, 0, 1));
  if (!c.linked) return [c.x, c.y, 0.45 + 0.55 * q];
  return [c.px + (c.x - c.px) * q, c.py + (c.y - c.py) * q, 0.45 + 0.55 * q];
}

/** A cell's opacity at age `a`. */
const cellAlpha = (a: number, reduced: boolean): number => clamp(a / (reduced ? FADE_IN_REDUCED : 0.25), 0, 1);

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
  /** Cells and further relations painted so far. */
  upTo: number;
  linksUpTo: number;
  /** Relation width in world units, fit for the view of the whole brain. */
  lineWidth: number;
}

const caches = new WeakMap<BrainDemo, Cache | null>();

function newCache(d: BrainDemo, v: View, hidden: string): Cache | null {
  const b = d.bounds;
  const k = (d.cells.length - 1) * 4;
  const pad = d.spacing * 2;
  const x0 = b[k] - pad,
    y0 = b[k + 1] - pad,
    w = b[k + 2] - b[k] + 2 * pad,
    h = b[k + 3] - b[k + 1] + 2 * pad;
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
    tint = canvas(0.5);
  if (!cells || !tint) return null;
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
    upTo: 0,
    linksUpTo: 0,
    lineWidth: Math.max(1.2, 0.9 / brainFitZoom(d, v, d.cells.length - 1)),
  };
}

/** The demo's cache, painted up to the cells settled by now; null without a 2D context. */
function cacheFor(d: BrainDemo, v: View, e: number, hidden: Set<string>): Cache | null {
  const sig = [...hidden].sort().join(',');
  let c = caches.get(d);
  if (c === undefined || (c && (c.start !== d.start || c.hidden !== sig))) {
    c = d.cells.length ? newCache(d, v, sig) : null;
    caches.set(d, c);
  }
  if (!c) return null;
  const settled = bornBy(d, e - (d.reduced ? FADE_IN_REDUCED : GLOW));
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
    if (cell.linked && !hidden.has(cell.domain)) line(cell.px, cell.py, cell.x, cell.y, cell.color);
  }
  while (c.linksUpTo < d.links.length && d.links[c.linksUpTo][1] < settled) {
    const [a, b] = d.links[c.linksUpTo++];
    const ca = d.cells[a],
      cb = d.cells[b];
    if (!hidden.has(ca.domain) && !hidden.has(cb.domain)) line(ca.x, ca.y, cb.x, cb.y, cb.color);
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
  if (cacheServes(cache, s, v)) {
    drawCached(v.ctx, cache, cache.tint, tintAlpha(s, v, d, t));
    return;
  }
  if (!beginLayer(v)) return;
  const [x0, y0, x1, y1] = viewRect(s, v, d.spacing * 2);
  const byColour = new Map<string, Path2D>();
  const r = d.spacing * TINT_R;
  for (let i = 0; i < n; i++) {
    const c = d.cells[i];
    if (hidden.has(c.domain) || c.x < x0 || c.x > x1 || c.y < y0 || c.y > y1) continue;
    if (e - c.born < BUD * 0.5) continue;
    let p = byColour.get(c.color);
    if (!p) byColour.set(c.color, (p = new Path2D()));
    p.moveTo(c.x + r, c.y);
    p.arc(c.x, c.y, r, 0, 6.283);
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
  const inView = (c: BrainCell) => c.x >= x0 && c.x <= x1 && c.y >= y0 && c.y <= y1;
  const zoom = s.cam.s;
  const width = cached ? cache.lineWidth : Math.max(1.2, 0.9 / zoom);

  // Relations: settled ones as one path per colour, growing ones one by one.
  const settled = new Map<string, Path2D>();
  const line = (ax: number, ay: number, bx: number, by: number, color: string) => {
    let p = settled.get(color);
    if (!p) settled.set(color, (p = new Path2D()));
    p.moveTo(ax, ay);
    p.lineTo(bx, by);
  };
  ctx.lineCap = 'round';
  for (let i = from; i < n; i++) {
    const c = d.cells[i];
    if (!c.linked || hidden.has(c.domain) || !inView(c)) continue;
    const a = e - c.born;
    if (a >= BUD || d.reduced) line(c.px, c.py, c.x, c.y, c.color);
    else {
      const [x, y] = at(c, a, false);
      ctx.strokeStyle = hex(themedColour(c.color), 0.5 * fade * clamp(a / 0.2, 0, 1));
      ctx.lineWidth = width;
      ctx.beginPath();
      ctx.moveTo(c.px, c.py);
      ctx.lineTo(x, y);
      ctx.stroke();
    }
  }
  for (let k = cached ? cache.linksUpTo : 0; k < d.links.length; k++) {
    const [a, b] = d.links[k];
    if (b >= n) break;
    const ca = d.cells[a],
      cb = d.cells[b];
    if (hidden.has(cb.domain) || hidden.has(ca.domain) || (!inView(ca) && !inView(cb))) continue;
    if (e - cb.born < BUD && !d.reduced) continue;
    line(ca.x, ca.y, cb.x, cb.y, cb.color);
  }
  ctx.lineWidth = width;
  for (const [color, p] of settled) {
    ctx.strokeStyle = hex(themedColour(color), LINK_ALPHA * fade);
    ctx.stroke(p);
  }

  // Glows: new cells while growing, a few firing ones once grown.
  if (!d.reduced) {
    const R = d.radius * 2.8;
    const glow = (x: number, y: number, k: number, color: string) => {
      const img = glowSprite(color);
      if (!img) return;
      ctx.globalAlpha = k * fade;
      ctx.drawImage(img, x - R, y - R, R * 2, R * 2);
    };
    for (let i = n - 1; i >= 0; i--) {
      const c = d.cells[i];
      const a = e - c.born;
      if (a >= GLOW) break;
      if (hidden.has(c.domain) || !inView(c)) continue;
      const [x, y] = at(c, a, false);
      glow(x, y, 1 - a / GLOW, c.color);
    }
    if (n >= d.cells.length)
      for (const c of d.cells) {
        const f = (e * FIRE_RATE + c.phase) % 1;
        if (f < FIRE_SHARE && !hidden.has(c.domain) && inView(c)) glow(c.x, c.y, Math.sin((f / FIRE_SHARE) * Math.PI), c.color);
      }
    ctx.globalAlpha = 1;
  }

  // Cells.
  const shownCells: [BrainCell, number, number, number, number][] = [];
  for (let i = from; i < n; i++) {
    const c = d.cells[i];
    if (hidden.has(c.domain) || !inView(c)) continue;
    const a = e - c.born;
    const [x, y, k] = at(c, a, d.reduced);
    const alpha = fade * cellAlpha(a, d.reduced);
    ctx.globalAlpha = alpha;
    drawSphere(ctx, c.color, x, y, d.radius * k);
    if (shownCells.length <= LABELS_MAX) shownCells.push([c, x, y, d.radius * k, alpha]);
  }
  ctx.globalAlpha = 1;

  // Names, close up: the oldest cells first, each name only where it overlaps none drawn yet.
  if (!cached && zoom >= LABEL_ZOOM && shownCells.length <= LABELS_MAX) {
    const k = labelScale(zoom);
    const size = Math.round(11 * k);
    ctx.textAlign = 'center';
    ctx.font = `500 ${size}px ${FONT_SANS}`;
    ctx.shadowColor = TH.shadow;
    ctx.shadowBlur = 4;
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
    ctx.shadowBlur = 0;
  }
}
