/**
 * The drawing surface: canvas, context, size, device pixel ratio, theme and the half-resolution
 * region layer. Ported from reference/ontaix-studio-reference.html lines 238-242, 253, 345-347
 * and 349 (`resize`, `panelW`, `CX`, `worldTransform`, `toWorld`, the offscreen layer).
 */
import type { CanvasTheme } from './themes';
import { themeFor } from './themes';
import type { Cam } from './types';

export interface View {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  off: HTMLCanvasElement;
  octx: CanvasRenderingContext2D;
  W: number;
  H: number;
  DPR: number;
  TH: CanvasTheme;
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
    TH: themeFor('light'),
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

export function worldTransform(v: View, cam: Cam): void {
  const { ctx } = v;
  ctx.setTransform(v.DPR, 0, 0, v.DPR, 0, 0);
  ctx.translate(CX(v), v.H / 2);
  ctx.scale(cam.s, cam.s);
  ctx.translate(-cam.x, -cam.y);
}

export const toWorld = (v: View, cam: Cam, sx: number, sy: number): [number, number] => [
  (sx - CX(v)) / cam.s + cam.x,
  (sy - v.H / 2) / cam.s + cam.y,
];
