/**
 * Convex hulls and the nearest-cell domain hit test. Ported from
 * reference/ontaix-studio-reference.html lines 348 (`hull`), 479-486 (`inHull`, `distSeg`,
 * `hitDomain`).
 */
import type { SceneState } from './state';
import type { Domain } from './types';
import { toWorld, type View } from './view';

export type Pt = [number, number];

/** Andrew's monotone chain; fewer than three points come back unchanged. */
export function hull(pts: Pt[]): Pt[] {
  if (pts.length < 3) return pts;
  pts = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o: Pt, a: Pt, b: Pt) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo: Pt[] = [],
    up: Pt[] = [];
  for (const p of pts) {
    while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop();
    lo.push(p);
  }
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i];
    while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop();
    up.push(p);
  }
  lo.pop();
  up.pop();
  return lo.concat(up);
}

export function inHull(pts: Pt[], x: number, y: number): boolean {
  if (pts.length < 3) return false;
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i][0],
      yi = pts[i][1],
      xj = pts[j][0],
      yj = pts[j][1];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = true;
  }
  return inside;
}

export function distSeg(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax,
    dy = by - ay;
  const l2 = dx * dx + dy * dy;
  const u = l2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2)) : 0;
  return Math.hypot(px - (ax + dx * u), py - (ay + dy * u));
}

/**
 * The domain whose tinted shape (hull grown by the padding) contains the world point; when
 * several do, the one whose nearest member is closest.
 */
export function hitDomainAt(s: SceneState, wx: number, wy: number): Domain | null {
  const pad = 86;
  let best: Domain | null = null,
    bd = 1e9;
  for (const d of s.DOMAINS) {
    if (d.hidden) continue;
    const members = s.nodes.filter((n) => n.domain === d && !n.dying);
    if (!members.length) continue;
    const pts = hull(members.map((n) => [n.x, n.y] as Pt));
    let dist: number;
    if (inHull(pts, wx, wy)) dist = 0;
    else {
      dist = 1e9;
      if (pts.length === 1) dist = Math.hypot(pts[0][0] - wx, pts[0][1] - wy);
      else
        for (let i = 0; i < pts.length; i++) {
          const a = pts[i],
            b = pts[(i + 1) % pts.length];
          if (pts.length === 2 && i === 1) break;
          dist = Math.min(dist, distSeg(wx, wy, a[0], a[1], b[0], b[1]));
        }
    }
    if (dist <= pad) {
      const near = Math.min(...members.map((n) => Math.hypot(n.x - wx, n.y - wy)));
      if (near < bd) {
        best = d;
        bd = near;
      }
    }
  }
  return best;
}

export function hitDomain(s: SceneState, v: View, sx: number, sy: number): Domain | null {
  const [wx, wy] = toWorld(v, s.cam, sx, sy);
  return hitDomainAt(s, wx, wy);
}
