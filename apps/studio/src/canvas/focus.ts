/**
 * Focus and hit testing: hover shows the neighbourhood, click is sticky focus, a domain focus
 * includes the cells of other domains it relates to. Ported from
 * reference/ontaix-studio-reference.html lines 336-337 (`dimOf`), 478 (`focusOnCell`), 487
 * (`focusOnDomain`), 488-490 (`hit`, `hitChip`, `hitAt`).
 */
import { neighbours, shown, type SceneState } from './state';
import type { Domain, Link, Node } from './types';
import { toWorld, type View } from './view';

/** Alpha factor of a node outside the focus set. */
export const dimOf = (s: SceneState, n: Node): number => (s.focusSet && !s.focusSet.has(n) ? 0.2 : 1);

export function focusOnCell(s: SceneState, n: Node | null): void {
  s.cellFocus = n;
  s.domainFocus = null;
  s.stickyFocus = n ? neighbours(s, n) : null;
  s.focusSet = s.stickyFocus;
  s.effects.arrangeTitle();
}

export function focusOnDomain(s: SceneState, d: Domain | null): void {
  s.domainFocus = d;
  setTimeout(() => s.effects.arrangeTitle(), 0);
  if (!d) {
    s.stickyFocus = null;
    s.focusSet = null;
    return;
  }
  const set = new Set(s.nodes.filter((n) => n.domain === d && !n.dying));
  for (const l of s.links) {
    if (set.has(l.a) && l.b.domain !== d) set.add(l.b);
    if (set.has(l.b) && l.a.domain !== d) set.add(l.a);
  }
  s.stickyFocus = set;
  s.focusSet = set;
}

/** The cell under a screen point, sources with a wider grab radius. */
export function hit(s: SceneState, v: View, sx: number, sy: number): Node | null {
  const [wx, wy] = toWorld(v, s.cam, sx, sy);
  let best: Node | null = null,
    bd = 1e9;
  for (const n of s.nodes) {
    if ((n.split && !n.split.broken) || !shown(n)) continue;
    const d = Math.hypot(n.x - wx, n.y - wy);
    if (d < n.r * (n.kind === 'source' ? 1.9 : 1.5) && d < bd) {
      best = n;
      bd = d;
    }
  }
  return best;
}

/** The link whose action chip is under a screen point. */
export function hitChip(s: SceneState, v: View, sx: number, sy: number): Link | null {
  const [wx, wy] = toWorld(v, s.cam, sx, sy);
  for (const l of s.links) {
    if (!l._chip || l.kind === 'clash' || l.pending || !shown(l.a) || !shown(l.b)) continue;
    if (Math.hypot(l._chip.x - wx, l._chip.y - wy) < (l._chip.r / Math.max(s.cam.s, 0.3)) * s.cam.s + 6) return l;
  }
  return null;
}

/** The cell under a world point, other than `except`; used as a drop target while dragging. */
export function hitAt(s: SceneState, wx: number, wy: number, except: Node | null): Node | null {
  let best: Node | null = null,
    bd = 1e9;
  for (const n of s.nodes) {
    if (n === except || (n.split && !n.split.broken) || n.dying || !shown(n)) continue;
    const d = Math.hypot(n.x - wx, n.y - wy);
    if (d < n.r * 1.6 && d < bd) {
      best = n;
      bd = d;
    }
  }
  return best;
}
