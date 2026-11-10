/**
 * Cells and sources: matte spheres with a rim, brass rounded squares, throb and recoil during
 * division, green and red flashes. Ported from reference/ontaix-studio-reference.html lines
 * 445-466 (`drawSource`, `drawCell`).
 */
import { clamp, hex, mix } from './colour';
import { MIX_BLACK, MIX_WHITE, themedColour } from '../design/tokens';
import { formatNumber, t } from '../i18n/i18n';
import { C } from './constants';
import { dimOf } from './focus';
import { drawCellLabels, drawSourceLabels, labelScale, MAX_GLYPH_EM, roundRect } from './labels';
import type { SceneState } from './state';
import type { Node } from './types';
import { inView, type View } from './view';

/** Screen pixels the 4 px label shadow can reach beyond the glyphs. */
const SHADOW_REACH = 8;

/** Sphere gradients by colour, opacity, fusion and radius: one gradient serves every cell drawn alike. */
const spheres = new Map<string, CanvasGradient>();
const SPHERES_MAX = 4096;

export function drawSource(s: SceneState, v: View, n: Node, t: number): void {
  const { ctx, TH } = v;
  const al =
    n.alpha *
    dimOf(s, n) *
    (n.pending ? 0.62 : 1) *
    (n.disabled ? 0.45 : 1) *
    (n.dying ? 1 - clamp((t - n.dying.start) / 0.7, 0, 1) : 1);
  const hot = n === s.hover,
    r = n.r;
  const fl = n.flash ? clamp((t - n.flash.start) / 0.9, 0, 1) : 0;
  const fk = n.flash ? Math.sin(fl * Math.PI) : 0;
  const flashColor = n.flash ? themedColour(n.flash.color) : null;
  if (fl >= 1) n.flash = null;
  ctx.save();
  ctx.translate(n.x, n.y);
  if (fk > 0 && flashColor) {
    ctx.strokeStyle = hex(flashColor, 0.9 * fk * al);
    ctx.lineWidth = 2;
    roundRect(ctx, -r - 1, -r - 1, 2 * r + 2, 2 * r + 2, 8);
    ctx.stroke();
  }
  const g = ctx.createLinearGradient(-r, -r, r, r);
  const brass = themedColour(s.BRASS);
  g.addColorStop(0, hex(mix(brass, MIX_WHITE, 0.2), 0.95 * al));
  g.addColorStop(1, hex(mix(brass, MIX_BLACK, 0.35), 0.95 * al));
  roundRect(ctx, -r, -r, 2 * r, 2 * r, 7);
  ctx.fillStyle = g;
  ctx.fill();
  ctx.strokeStyle = hex(mix(brass, MIX_WHITE, 0.35), (hot ? 0.9 : 0.5) * al);
  ctx.lineWidth = hot ? 1.6 : 1;
  ctx.stroke();
  for (let i = -1; i <= 1; i++) {
    ctx.fillStyle = `rgba(${TH.CHIP},${0.55 * al})`;
    ctx.fillRect(-r * 0.55, i * r * 0.36 - 1.1, r * 1.1, 2.2);
  }
  ctx.restore();
  drawSourceLabels(s, v, n, al, r, hot);
}

export function drawCell(s: SceneState, v: View, n: Node, t: number): void {
  if (n.kind === 'source') return drawSource(s, v, n, t);
  const { ctx, TH } = v;
  const dim = dimOf(s, n);
  const dyK = n.dying ? clamp((t - n.dying.start) / 0.7, 0, 1) : 0;
  const al =
    n.alpha * dim * (1 - dyK) * (n.pending ? 0.62 : 1) * (s.COVERAGE && n.kind === 'concept' && !n.bound ? 0.38 : 1);
  const hot = n === s.hover;
  const own = themedColour(n.color);
  const col = n.conflict ? mix(own, themedColour(C.conflict), 0.55 + 0.35 * Math.sin(t * 7)) : own;
  const r = n.r * (1 - 0.3 * dyK);
  const fl = n.flash ? clamp((t - n.flash.start) / 0.9, 0, 1) : 0;
  const fk = n.flash ? Math.sin(fl * Math.PI) : 0;
  if (fl >= 1) n.flash = null;
  const fcol = n.flash ? themedColour(n.flash.color) : n.dying?.color ? themedColour(n.dying.color) : null;
  const parentSplit = s.splitting.get(n);
  const fused = (n.split && !n.split.broken) || (parentSplit && !parentSplit.broken);
  let sx = 1,
    sy = 1,
    rot = 0;
  {
    const sp = n.split ? n.split : parentSplit;
    if (sp && sp.p !== undefined && sp.p < 0.2) {
      const th = 1 + 0.08 * Math.sin((sp.p / 0.2) * Math.PI * 2) * (1 - (sp.p / 0.2) * 0.4);
      sx = sy = th;
    }
  }
  if (n === s.dropTarget && s.dragging) {
    ctx.strokeStyle = `rgba(${TH.INK},0.9)`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(n.x, n.y, r + 1, 0, 6.283);
    ctx.stroke();
  }
  if (n.recoil) {
    const q = (t - n.recoil.start) / 0.45;
    if (q >= 1) n.recoil = null;
    else {
      const k = 0.2 * Math.sin(q * Math.PI * 2) * (1 - q);
      rot = n.recoil.ang;
      sx *= 1 - k;
      sy *= 1 + k;
    }
  }
  ctx.save();
  ctx.translate(n.x, n.y);
  ctx.rotate(rot);
  ctx.scale(sx, sy);
  ctx.fillStyle = sphere(ctx, col, al, !!fused, r);
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, 6.283);
  ctx.fill();
  if (!fused) {
    const rc = fcol && (fk > 0 || dyK > 0) ? fcol : mix(col, MIX_WHITE, 0.35);
    ctx.strokeStyle = hex(rc, ((fcol ? 0.9 : hot ? 0.7 : 0.35) * al) / (n.pending ? 0.62 : 1));
    ctx.lineWidth = fcol ? 1.8 : hot ? 1.6 : 1;
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, 6.283);
    ctx.stroke();
  }
  ctx.restore();
  drawCellLabels(s, v, n, al, col, r, hot);
}

/**
 * True when some pixel of the cell, its rim or the text under it can fall on the canvas. The
 * bound is generous: the body may throb and recoil to 1.3 times its radius, every line of text
 * is taken as wide as its longest possible glyphs, and the label shadow adds its reach. A
 * source is always drawn.
 */
export function cellInView(s: SceneState, v: View, n: Node): boolean {
  if (n.kind === 'source') return true;
  const body = n.r * 1.3 + 3;
  let half = body,
    bottom = body;
  if (s.cam.s > 0.3) {
    const k = labelScale(s.cam.s);
    let widest = n.label.length * (n.kind === 'root' ? 15 : 13) * k;
    widest = Math.max(widest, (n.sub || t('canvas.cell.awaitingApproval')).length * 11 * k);
    if (n.bound)
      widest = Math.max(
        widest,
        t('canvas.cell.bound', { records: formatNumber(n.bound.records), source: n.bound.source.label, fresh: n.bound.fresh }).length * 10.5 * k,
      );
    else if (s.COVERAGE) widest = Math.max(widest, t('canvas.cell.noData').length * 10.5 * k);
    half = Math.max(half, (widest * MAX_GLYPH_EM) / 2);
    // Three baselines at most, 24, 39 and 53 label units under the body, plus a line of glyphs.
    bottom = n.r + 72 * k;
  }
  return inView(v, n.x - half, n.y - body, n.x + half, n.y + bottom, SHADOW_REACH / s.cam.s + 4);
}

/** The matte sphere gradient of a cell of colour `col` at opacity `al`, in the cell's own coordinates. */
function sphere(ctx: CanvasRenderingContext2D, col: string, al: number, fused: boolean, r: number): CanvasGradient {
  const key = `${col}|${al}|${fused ? 1 : 0}|${r}`;
  let g = spheres.get(key);
  if (g) return g;
  if (spheres.size >= SPHERES_MAX) spheres.clear();
  g = ctx.createRadialGradient(-r * 0.35, -r * 0.35, r * 0.1, 0, 0, r * 1.04);
  g.addColorStop(0, hex(mix(col, MIX_WHITE, 0.55), 0.98 * al));
  g.addColorStop(0.3, hex(mix(col, MIX_WHITE, 0.18), 0.98 * al));
  g.addColorStop(0.75, hex(col, 0.96 * al));
  g.addColorStop(1, hex(mix(col, MIX_BLACK, fused ? 0.38 : 0.42), 0.96 * al));
  spheres.set(key, g);
  return g;
}
