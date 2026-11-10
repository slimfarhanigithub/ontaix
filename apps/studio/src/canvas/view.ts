/**
 * The drawing surface: canvas, context, size, device pixel ratio, the canvas theme and the
 * half-resolution
 * region layer. Ported from reference/ontaix-studio-reference.html lines 238-242, 253, 345-347
 * and 349 (`resize`, `panelW`, `CX`, `worldTransform`, `toWorld`, the offscreen layer).
 */
import type { CanvasTheme } from './themes';
import { canvasTheme } from './themes';
import type { Cam } from './types';

/** A rectangle in world units: left, top, right, bottom. */
export type WorldRect = [number, number, number, number];

export interface View {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  off: HTMLCanvasElement;
  octx: CanvasRenderingContext2D;
  W: number;
  H: number;
  DPR: number;
  TH: CanvasTheme;
  /** The world rectangle the whole canvas shows under the last world transform. */
  world: WorldRect;
  /** True while the changes panel is hidden (`body.panel-off`). */
  panelOff: () => boolean;
  /** Viewport size in CSS pixels. */
  viewport: () => [number, number];
}

export function createView(canvas: HTMLCanvasElement): View {
  const ctx = canvas.getContext('2d');
  const off = document.createElement('canvas');
  const octx = off.getContext('2d');
  if (!ctx || !octx) throw new Error('2d canvas context is not available');
  const v: View = {
    canvas,
    ctx,
    off,
    octx,
    W: 0,
    H: 0,
    DPR: 1,
    TH: canvasTheme(),
    world: [0, 0, 0, 0],
    panelOff: () => document.body.classList.contains('panel-off'),
    viewport: () => [innerWidth, innerHeight],
  };
  resize(v);
  return v;
}

export function resize(v: View): void {
  const [iw, ih] = v.viewport();
  v.DPR = Math.min(devicePixelRatio || 1, 2);
  v.W = Math.max(1, iw);
  v.H = Math.max(1, ih);
  v.canvas.width = Math.max(1, Math.round(v.W * v.DPR));
  v.canvas.height = Math.max(1, Math.round(v.H * v.DPR));
}

/** Width the changes panel takes from the canvas: 320 above the compact breakpoint while shown. */
export const panelW = (v: View): number => (v.W > 900 && !v.panelOff() ? 320 : 0);

/** Horizontal centre of the free canvas area. */
export const CX = (v: View): number => (v.W - panelW(v)) / 2;

/**
 * The camera eases toward its target without ever quite reaching it, and the cells it fits
 * settle the same way, so the camera keeps changing by amounts far below a pixel. The transform
 * is set on a grid of this step, in zoom and in world units, so that a camera within the step of
 * where it was draws with exactly the same transform: the browser then reuses every glyph and
 * every text shape it rasterised for the last frame instead of drawing them all again. The step
 * moves nothing by more than a few thousandths of a pixel.
 */
const TRANSFORM_STEP = 1e-6;
const onStep = (value: number): number => Math.round(value / TRANSFORM_STEP) * TRANSFORM_STEP;

export function worldTransform(v: View, cam: Cam): void {
  const { ctx } = v;
  const s = onStep(cam.s),
    x = onStep(cam.x),
    y = onStep(cam.y);
  ctx.setTransform(v.DPR, 0, 0, v.DPR, 0, 0);
  ctx.translate(CX(v), v.H / 2);
  ctx.scale(s, s);
  ctx.translate(-x, -y);
  const [x0, y0] = toWorld(v, cam, 0, 0),
    [x1, y1] = toWorld(v, cam, v.W, v.H);
  v.world = [x0, y0, x1, y1];
}

export const toWorld = (v: View, cam: Cam, sx: number, sy: number): [number, number] => [
  (sx - CX(v)) / cam.s + cam.x,
  (sy - v.H / 2) / cam.s + cam.y,
];

/** True when a box in world units, grown by `pad` on every side, reaches the canvas. */
export const inView = (v: View, x0: number, y0: number, x1: number, y1: number, pad: number): boolean =>
  x1 + pad >= v.world[0] && x0 - pad <= v.world[2] && y1 + pad >= v.world[1] && y0 - pad <= v.world[3];
