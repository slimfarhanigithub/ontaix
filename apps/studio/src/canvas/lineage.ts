/**
 * Lineage: where a concept comes from and what came from it. Ported from
 * reference/ontaix-studio-reference.html lines 584 (`descends`), 649-651 (`ancestorsOf`,
 * `childrenOf`, `descendantsOf`) and the state part of 653-663 (`showLineage`, `hideLineage`).
 */
import { neighbours, type SceneState } from './state';
import type { Node } from './types';

export const ancestorsOf = (n: Node): Node[] => {
  const out: Node[] = [];
  let c = n.parent;
  let g = 0;
  while (c && g++ < 60) {
    out.unshift(c);
    c = c.parent;
  }
  return out;
};

export const childrenOf = (s: SceneState, n: Node): Node[] => s.nodes.filter((x) => x.parent === n && !x.dying);

export const descendantsOf = (s: SceneState, n: Node): Node[] => {
  const out: Node[] = [];
  const walk = (x: Node) => {
    for (const k of childrenOf(s, x)) {
      out.push(k);
      walk(k);
    }
  };
  walk(n);
  return out;
};

/** True when `n` descends from `anc` through `isa` links or incoming `rel` birth links. */
export function descends(s: SceneState, n: Node, anc: Node): boolean {
  let c: Node | null = n;
  for (let k = 0; k < 50 && c; k++) {
    const cur: Node = c;
    const l = s.links.find((x) => (x.kind === 'isa' && x.a === cur) || (x.kind === 'rel' && x.b === cur && x.a !== cur));
    if (!l) return false;
    c = l.kind === 'isa' ? l.b : l.a;
    if (c === anc) return true;
  }
  return false;
}

/** The cell, its ancestors, its descendants and the sources feeding the cell or a descendant. */
export function lineageSetOf(s: SceneState, n: Node): Set<Node> {
  const anc = ancestorsOf(n),
    desc = descendantsOf(s, n);
  const set = new Set<Node>([n, ...anc, ...desc]);
  if (n.bound) set.add(n.bound.source);
  for (const d of desc) if (d.bound) set.add(d.bound.source);
  return set;
}

/** Puts the lineage of `n` in focus. */
export function showLineageState(s: SceneState, n: Node): Set<Node> {
  s.lineageNode = n;
  s.effects.arrangeTitle();
  const set = lineageSetOf(s, n);
  s.lineageSet = set;
  s.stickyFocus = set;
  s.focusSet = set;
  return set;
}

/** Releases the lineage focus, back to the cell focus when the drawer still shows that cell. */
export function hideLineageState(s: SceneState, drawerNode: Node | null): void {
  s.lineageNode = null;
  s.lineageSet = null;
  s.effects.arrangeTitle();
  if (s.cellFocus && drawerNode === s.cellFocus) {
    s.stickyFocus = neighbours(s, s.cellFocus);
    s.focusSet = s.stickyFocus;
  } else {
    s.stickyFocus = null;
    s.focusSet = null;
  }
}
