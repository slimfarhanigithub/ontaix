/**
 * Cells and sources: matte spheres with a rim, brass rounded squares, throb and recoil during
 * division, green and red flashes. Ported from reference/ontaix-studio-reference.html lines
 * 445-466 (`drawSource`, `drawCell`).
 */
import { clamp, hex, mix } from './colour';
import { C } from './constants';
import { dimOf } from './focus';
import { drawCellLabels, drawSourceLabels, roundRect } from './labels';
import type { SceneState } from './state';
import type { Node } from './types';
import type { View } from './view';

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
  const flashColor = n.flash ? n.flash.color : null;
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
  g.addColorStop(0, hex(mix(s.BRASS, '#ffffff', 0.2), 0.95 * al));
  g.addColorStop(1, hex(mix(s.BRASS, '#000000', 0.35), 0.95 * al));
  roundRect(ctx, -r, -r, 2 * r, 2 * r, 7);
  ctx.fillStyle = g;
  ctx.fill();
  ctx.strokeStyle = hex(mix(s.BRASS, '#ffffff', 0.35), (hot ? 0.9 : 0.5) * al);
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
  const { ctx } = v;
  const dim = dimOf(s, n);
  const dyK = n.dying ? clamp((t - n.dying.start) / 0.7, 0, 1) : 0;
  const al =
    n.alpha * dim * (1 - dyK) * (n.pending ? 0.62 : 1) * (s.COVERAGE && n.kind === 'concept' && !n.bound ? 0.38 : 1);
  const hot = n === s.hover;
  const col = n.conflict ? mix(n.color, C.conflict, 0.55 + 0.35 * Math.sin(t * 7)) : n.color;
  const r = n.r * (1 - 0.3 * dyK);
  const fl = n.flash ? clamp((t - n.flash.start) / 0.9, 0, 1) : 0;
  const fk = n.flash ? Math.sin(fl * Math.PI) : 0;
  if (fl >= 1) n.flash = null;
  const fcol = n.flash ? n.flash.color : n.dying ? n.dying.color : null;
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
    ctx.strokeStyle = 'rgba(255,255,255,0.9)';
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
  const cg = ctx.createRadialGradient(-r * 0.35, -r * 0.35, r * 0.1, 0, 0, r * 1.04);
  cg.addColorStop(0, hex(mix(col, '#ffffff', 0.55), 0.98 * al));
  cg.addColorStop(0.3, hex(mix(col, '#ffffff', 0.18), 0.98 * al));
  cg.addColorStop(0.75, hex(col, 0.96 * al));
  cg.addColorStop(1, hex(mix(col, '#000000', fused ? 0.38 : 0.42), 0.96 * al));
  ctx.fillStyle = cg;
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, 6.283);
  ctx.fill();
  if (!fused) {
    const rc = fcol && (fk > 0 || dyK > 0) ? fcol : mix(col, '#ffffff', 0.35);
    ctx.strokeStyle = hex(rc, ((fcol ? 0.9 : hot ? 0.7 : 0.35) * al) / (n.pending ? 0.62 : 1));
    ctx.lineWidth = fcol ? 1.8 : hot ? 1.6 : 1;
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, 6.283);
    ctx.stroke();
  }
  ctx.restore();
  drawCellLabels(s, v, n, al, col, r, hot);
}
