/**
 * Directed relations: quadratic curves brighter toward the target, arrow heads, dashes for
 * `isa` and `same`, jitter for `clash`, and the action chip. Ported from
 * reference/ontaix-studio-reference.html lines 338-341 (`qp`, `qt`, `curve`) and 377-396
 * (`drawLinks`).
 */
import { random } from '../runtime/rng';
import { clamp, ease, hex } from './colour';
import { C, EQUIVALENCE_LINE, MOTION } from './constants';
import { dimOf } from './focus';
import { roundRect } from './labels';
import { shown, type SceneState } from './state';
import type { Link } from './types';
import type { View } from './view';

/** Point on the quadratic curve of a link at parameter `u`. */
export const qp = (l: Link, cx: number, cy: number, u: number): [number, number] => [
  (1 - u) * (1 - u) * l.a.x + 2 * (1 - u) * u * cx + u * u * l.b.x,
  (1 - u) * (1 - u) * l.a.y + 2 * (1 - u) * u * cy + u * u * l.b.y,
];

/** Tangent of the quadratic curve at `u`. */
export const qt = (l: Link, cx: number, cy: number, u: number): [number, number] => [
  2 * (1 - u) * (cx - l.a.x) + 2 * u * (l.b.x - cx),
  2 * (1 - u) * (cy - l.a.y) + 2 * u * (l.b.y - cy),
];

/** Control point of a link, bent by its seed. */
export const curve = (l: Link): { cx: number; cy: number } => {
  const mx = (l.a.x + l.b.x) / 2,
    my = (l.a.y + l.b.y) / 2,
    dx = l.b.x - l.a.x,
    dy = l.b.y - l.a.y,
    k = (l.seed - 0.5) * 0.3;
  return { cx: mx - dy * k, cy: my + dx * k };
};

export function drawLinks(s: SceneState, v: View, t: number): void {
  const { ctx, TH } = v;
  for (const l of s.links) {
    if (l.a.split || l.b.split || !shown(l.a) || !shown(l.b)) continue;
    const { cx, cy } = curve(l);
    const isa = l.kind === 'isa',
      clash = l.kind === 'clash';
    let g = 1;
    if (l.grow) {
      g = s.SKIP ? 1 : clamp((t - l.grow.start) / 0.3, 0, 1);
      if (g >= 1) l.grow = null;
    }
    const dy = (n: Link['a']) => (n.dying ? 1 - clamp((t - n.dying.start) / 0.7, 0, 1) : 1);
    const pend = l.pending || l.a.pending || l.b.pending;
    const lf = l.dying ? 1 - clamp((t - l.dying.start) / 0.7, 0, 1) : 1;
    const same = l.kind === 'same',
      bind = l.kind === 'bind';
    const col = isa ? l.a.color : clash ? C.conflict : same ? EQUIVALENCE_LINE : bind ? s.BRASS : l.b.color;
    const al =
      Math.min(1, l.alpha * 1.6) * Math.min(dimOf(s, l.a), dimOf(s, l.b)) * dy(l.a) * dy(l.b) * (pend ? 0.55 : 1) * lf;
    const chord = Math.hypot(l.b.x - l.a.x, l.b.y - l.a.y) || 1;
    const u0 = clamp((l.a.r * 1.05) / chord, 0, 0.45);
    let u1 = clamp(1 - (l.b.r * 1.05 + 10) / chord, 0.55, 1);
    u1 = u0 + (u1 - u0) * ease(g);
    const [ax, ay] = qp(l, cx, cy, u0),
      [bx, by] = qp(l, cx, cy, u1);
    const grad = ctx.createLinearGradient(ax, ay, bx, by);
    grad.addColorStop(0, hex(col, 0.22 * al));
    grad.addColorStop(1, hex(col, 0.8 * al));
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    if (clash) {
      for (let i = 1; i <= 14; i++) {
        const u = u0 + ((u1 - u0) * i) / 14;
        const [x, y] = qp(l, cx, cy, u);
        ctx.lineTo(x + (random() - 0.5) * 7 * MOTION, y + (random() - 0.5) * 7 * MOTION);
      }
    } else {
      const p01x = l.a.x + (cx - l.a.x) * u0,
        p01y = l.a.y + (cy - l.a.y) * u0,
        p12x = cx + (l.b.x - cx) * u0,
        p12y = cy + (l.b.y - cy) * u0;
      ctx.quadraticCurveTo(p01x + (p12x - p01x) * u1, p01y + (p12y - p01y) * u1, bx, by);
    }
    const inLine =
      s.lineageSet &&
      s.lineageSet.has(l.a) &&
      s.lineageSet.has(l.b) &&
      (l.b.parent === l.a || l.a.parent === l.b || bind);
    ctx.lineCap = 'round';
    ctx.lineWidth = inLine ? 2.2 : same || bind ? 1 : 1.3;
    ctx.strokeStyle = clash ? hex(C.conflict, 0.85 * al) : same ? hex(col, 0.55 * al) : bind ? hex(col, 0.5 * al) : grad;
    if (isa) ctx.setLineDash([6, 5]);
    else if (same) ctx.setLineDash([2, 5]);
    ctx.stroke();
    ctx.setLineDash([]);
    if (g >= 1 && Math.hypot(l.b.x - l.a.x, l.b.y - l.a.y) - l.a.r - l.b.r > 26) {
      const [tx, ty] = qt(l, cx, cy, u1);
      const an = Math.atan2(ty, tx),
        sz = isa ? 11 : 8;
      const head = () => {
        ctx.beginPath();
        ctx.moveTo(sz, 0);
        ctx.lineTo(-sz * 0.15, sz * 0.55);
        ctx.lineTo(-sz * 0.15, -sz * 0.55);
        ctx.closePath();
      };
      ctx.save();
      ctx.translate(bx, by);
      ctx.rotate(an);
      head();
      if (isa) {
        ctx.fillStyle = `rgba(${TH.CHIP},0.95)`;
        ctx.fill();
        ctx.strokeStyle = hex(col, 0.95 * al);
        ctx.lineWidth = 1.4;
        ctx.stroke();
      } else {
        ctx.fillStyle = hex(col, 0.95 * al);
        ctx.fill();
      }
      ctx.restore();
      if (clash || same) {
        const [tx2, ty2] = qt(l, cx, cy, u0);
        ctx.save();
        ctx.translate(ax, ay);
        ctx.rotate(Math.atan2(ty2, tx2) + Math.PI);
        head();
        ctx.fillStyle = hex(clash ? C.conflict : col, 0.95 * al);
        ctx.fill();
        ctx.restore();
      }
    } else {
      const tg = ctx.createRadialGradient(bx, by, 0, bx, by, 8);
      tg.addColorStop(0, hex(col, 0.8 * al));
      tg.addColorStop(1, hex(col, 0));
      ctx.fillStyle = tg;
      ctx.beginPath();
      ctx.arc(bx, by, 8, 0, 6.283);
      ctx.fill();
    }

    const gap = Math.hypot(l.b.x - l.a.x, l.b.y - l.a.y) - l.a.r - l.b.r;
    if (gap < 26) continue;
    if (
      l.label &&
      s.cam.s > 0.5 &&
      al > 0.3 &&
      g >= 1 &&
      gap > 70 &&
      !(bind && !(s.focusSet && s.focusSet.has(l.a) && s.focusSet.has(l.b)))
    ) {
      const [mx, my] = qp(l, cx, cy, (u0 + u1) / 2);
      const [tx, ty] = qt(l, cx, cy, 0.5);
      let an = Math.atan2(ty, tx);
      if (an > Math.PI / 2 || an < -Math.PI / 2) an += Math.PI;
      ctx.save();
      ctx.translate(mx, my);
      ctx.rotate(an);
      ctx.font = `${isa ? '300' : '500'} 10.5px Sora, sans-serif`;
      const w = ctx.measureText(l.label).width + 16;
      l._chip = { x: mx, y: my, r: Math.max(w / 2, 12) };
      roundRect(ctx, -w / 2, -9, w, 18, 9);
      ctx.fillStyle = `rgba(${TH.CHIP},0.9)`;
      ctx.fill();
      ctx.strokeStyle = hex(col, 0.45 * al);
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = clash ? hex(C.conflict, 0.95 * al) : `rgba(${TH.INK},${(same ? 0.75 : 0.92) * al})`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(l.label, 0, 1);
      ctx.textBaseline = 'alphabetic';
      ctx.restore();
    }
  }
}
