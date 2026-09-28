/**
 * The metaball neck between a dividing parent and its child, with the cleavage furrow.
 * Ported from reference/ontaix-studio-reference.html lines 405-416 (`drawNeck`).
 */
import { clamp, hex, mix } from './colour';
import { dimOf } from './focus';
import type { SceneState } from './state';
import type { Node } from './types';
import type { View } from './view';

export function drawNeck(s: SceneState, v: View, n: Node, t: number): void {
  const { ctx } = v;
  const m = n.split;
  if (!m || m.broken) return;
  const c1 = m.from,
    c2 = n,
    r1 = c1.r,
    r2 = c2.r;
  const d = Math.hypot(c2.x - c1.x, c2.y - c1.y);
  if (d < 1) return;
  const p = clamp((t - m.start) / m.dur, 0, 1),
    q = clamp((p - 0.2) / 0.8, 0, 1),
    vv = 0.64 - 0.5 * clamp((q - 0.25) / 0.55, 0, 1);
  const maxDist = (r1 + r2) * 1.3;
  if (d > maxDist || d <= (r1 + r2) * 0.5) return;
  const neckAlpha = clamp((d - (r1 + r2) * 0.5) / ((r1 + r2) * 0.3), 0, 1);
  let u1 = 0,
    u2 = 0;
  if (d < r1 + r2) {
    u1 = Math.acos(clamp((r1 * r1 + d * d - r2 * r2) / (2 * r1 * d), -1, 1));
    u2 = Math.acos(clamp((r2 * r2 + d * d - r1 * r1) / (2 * r2 * d), -1, 1));
  }
  const a = Math.atan2(c2.y - c1.y, c2.x - c1.x),
    maxSpread = Math.acos(clamp((r1 - r2) / d, -1, 1));
  const a1 = a + u1 + (maxSpread - u1) * vv,
    a2 = a - u1 - (maxSpread - u1) * vv,
    a3 = a + Math.PI - u2 - (Math.PI - u2 - maxSpread) * vv,
    a4 = a - Math.PI + u2 + (Math.PI - u2 - maxSpread) * vv;
  const P = (c: Node, r: number, an: number): [number, number] => [c.x + Math.cos(an) * r, c.y + Math.sin(an) * r];
  const p1 = P(c1, r1, a1),
    p2 = P(c1, r1, a2),
    p3 = P(c2, r2, a3),
    p4 = P(c2, r2, a4);
  const d2 = Math.min(vv * 2.4, Math.hypot(p1[0] - p3[0], p1[1] - p3[1]) / (r1 + r2)) * Math.min(1, (d * 2) / (r1 + r2));
  const r1b = r1 * d2,
    r2b = r2 * d2;
  const h1 = [p1[0] + Math.cos(a1 - Math.PI / 2) * r1b, p1[1] + Math.sin(a1 - Math.PI / 2) * r1b],
    h2 = [p2[0] + Math.cos(a2 + Math.PI / 2) * r1b, p2[1] + Math.sin(a2 + Math.PI / 2) * r1b],
    h3 = [p3[0] + Math.cos(a3 + Math.PI / 2) * r2b, p3[1] + Math.sin(a3 + Math.PI / 2) * r2b],
    h4 = [p4[0] + Math.cos(a4 - Math.PI / 2) * r2b, p4[1] + Math.sin(a4 - Math.PI / 2) * r2b];
  const col = c1.color,
    al = c1.alpha * dimOf(s, c1) * neckAlpha;
  const nx = -Math.sin(a),
    ny = Math.cos(a),
    mx = (c1.x + c2.x) / 2,
    my = (c1.y + c2.y) / 2,
    w = Math.max(r1, r2);
  const g = ctx.createLinearGradient(mx + nx * w, my + ny * w, mx - nx * w, my - ny * w);
  g.addColorStop(0, hex(mix(col, '#000000', 0.38), 0.96 * al));
  g.addColorStop(0.35, hex(mix(col, '#ffffff', 0.16), 0.97 * al));
  g.addColorStop(0.65, hex(col, 0.97 * al));
  g.addColorStop(1, hex(mix(col, '#000000', 0.38), 0.96 * al));
  ctx.beginPath();
  ctx.moveTo(p1[0], p1[1]);
  ctx.bezierCurveTo(h1[0], h1[1], h3[0], h3[1], p3[0], p3[1]);
  ctx.lineTo(p4[0], p4[1]);
  ctx.bezierCurveTo(h4[0], h4[1], h2[0], h2[1], p2[0], p2[1]);
  ctx.closePath();
  ctx.fillStyle = g;
  ctx.fill();
  const fur = clamp((q - 0.3) / 0.5, 0, 1);
  if (fur > 0) {
    const hw = Math.hypot(p1[0] - p2[0], p1[1] - p2[1]) * 0.5;
    const fg = ctx.createLinearGradient(
      mx - Math.cos(a) * 6,
      my - Math.sin(a) * 6,
      mx + Math.cos(a) * 6,
      my + Math.sin(a) * 6,
    );
    fg.addColorStop(0, hex('#000000', 0));
    fg.addColorStop(0.5, hex('#000000', 0.28 * fur * al));
    fg.addColorStop(1, hex('#000000', 0));
    ctx.fillStyle = fg;
    ctx.beginPath();
    ctx.moveTo(mx + nx * hw * 1.2 - Math.cos(a) * 6, my + ny * hw * 1.2 - Math.sin(a) * 6);
    ctx.lineTo(mx + nx * hw * 1.2 + Math.cos(a) * 6, my + ny * hw * 1.2 + Math.sin(a) * 6);
    ctx.lineTo(mx - nx * hw * 1.2 + Math.cos(a) * 6, my - ny * hw * 1.2 + Math.sin(a) * 6);
    ctx.lineTo(mx - nx * hw * 1.2 - Math.cos(a) * 6, my - ny * hw * 1.2 - Math.sin(a) * 6);
    ctx.closePath();
    ctx.fill();
  }
}
