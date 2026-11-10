/**
 * The demo brain's painted pieces, shared by the brain and its rig: a cell's sphere, a soft halo,
 * a spark of light, and the sparks of a frame batched so thousands stay smooth. Each is painted
 * once per colour into a small canvas and copied from then on.
 */
import { MIX_BLACK, MIX_WHITE, themedColour } from '../design/tokens';
import { hex, mix } from '../canvas/colour';

/** Pixel radius of the painted sphere each cell is a copy of, of a halo and of a spark. */
export const SPRITE_R = 32;
/** A spark's streak length as a share of its way, its spark's radius and its streak's width in CSS pixels, and the streak's opacity. */
const PULSE_TAIL = 0.14;
const PULSE_SPARK_PX = 7;
const PULSE_WIDTH_PX = 1.4;
const PULSE_TAIL_ALPHA = 0.5;

const sprites = new Map<string, HTMLCanvasElement | null>();
const glowSprites = new Map<string, HTMLCanvasElement | null>();
const sparkSprites = new Map<string, HTMLCanvasElement | null>();

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
export function sprite(color: string): HTMLCanvasElement | null {
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

/** The soft halo of a colour: a new cell's, a lit cell's, a core's. */
export function glowSprite(color: string): HTMLCanvasElement | null {
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

/** The spark at the head of a light: near white at its heart, then its colour, fading out. */
function sparkSprite(color: string): HTMLCanvasElement | null {
  if (!sparkSprites.has(color))
    sparkSprites.set(
      color,
      paint(SPRITE_R * 2, (g) => {
        const col = themedColour(color);
        const gr = g.createRadialGradient(0, 0, 0, 0, 0, SPRITE_R);
        gr.addColorStop(0, hex(mix(col, MIX_WHITE, 0.85), 1));
        gr.addColorStop(0.16, hex(mix(col, MIX_WHITE, 0.35), 0.95));
        gr.addColorStop(0.45, hex(col, 0.35));
        gr.addColorStop(1, hex(col, 0));
        g.fillStyle = gr;
        g.fillRect(-SPRITE_R, -SPRITE_R, SPRITE_R * 2, SPRITE_R * 2);
      }),
    );
  return sparkSprites.get(color) ?? null;
}

/** Draws a cell's sphere centred on x, y with radius r, or a flat disc without sprites. */
export function drawSphere(g: CanvasRenderingContext2D, color: string, x: number, y: number, r: number): void {
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

/** Draws a halo of `color` centred on x, y, `R` in radius. */
export function drawGlow(g: CanvasRenderingContext2D, color: string, x: number, y: number, R: number, alpha: number): void {
  const img = glowSprite(color);
  if (!img || alpha <= 0.01) return;
  g.globalAlpha = alpha;
  g.drawImage(img, x - R, y - R, R * 2, R * 2);
  g.globalAlpha = 1;
}

/**
 * The lights of a frame: their streaks gathered in one path per colour and opacity, their sparks
 * drawn one by one over the cells. A spark is at least PULSE_SPARK_PX on screen, larger when asked.
 */
export class Pulses {
  private streaks = new Map<string, { color: string; alpha: number; width: number; path: Path2D }>();
  private sparks: [string, number, number, number, number][] = [];

  /** A light heading from ax, ay to bx, by, `q` of the way there, a streak in `tail` behind a spark in `head`. */
  add(tail: string, head: string, ax: number, ay: number, bx: number, by: number, q: number, alpha: number, r = 0): void {
    const q0 = Math.max(0, q - PULSE_TAIL);
    this.segment(tail, head, ax + (bx - ax) * q0, ay + (by - ay) * q0, ax + (bx - ax) * q, ay + (by - ay) * q, alpha, r);
  }

  /** A light whose streak runs from x0, y0 to its spark at x1, y1, `r` world units at least in radius. */
  segment(tail: string, head: string, x0: number, y0: number, x1: number, y1: number, alpha: number, r = 0, width = 0): void {
    if (alpha <= 0.01) return;
    const a = Math.round(alpha * 10) / 10;
    const key = `${tail}|${a}|${width}`;
    let st = this.streaks.get(key);
    if (!st) this.streaks.set(key, (st = { color: tail, alpha: a, width, path: new Path2D() }));
    st.path.moveTo(x0, y0);
    st.path.lineTo(x1, y1);
    this.sparks.push([head, x1, y1, alpha, r]);
  }

  drawStreaks(g: CanvasRenderingContext2D, zoom: number): void {
    g.lineCap = 'round';
    for (const st of this.streaks.values()) {
      g.lineWidth = Math.max(PULSE_WIDTH_PX / zoom, st.width);
      g.strokeStyle = hex(themedColour(st.color), PULSE_TAIL_ALPHA * st.alpha);
      g.stroke(st.path);
    }
  }

  drawSparks(g: CanvasRenderingContext2D, zoom: number): void {
    for (const [color, x, y, alpha, r] of this.sparks) {
      const img = sparkSprite(color);
      if (!img) continue;
      const R = Math.max(PULSE_SPARK_PX / zoom, r);
      g.globalAlpha = alpha;
      g.drawImage(img, x - R, y - R, R * 2, R * 2);
    }
    g.globalAlpha = 1;
  }
}
