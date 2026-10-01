/**
 * Readability metrics of the scene as it is drawn: every living, shown cell and the links
 * between them, at their positions (or at the end of their arrange tween).
 */
import { cellFootprint, chipWidth, estimateWidth, type Measure } from './footprint';
import { measureLayout, type LayoutMetrics, type MetricCell, type MetricLink } from './layoutMetrics';
import { shown, type SceneState } from './state';
import type { Node } from './types';

/** Metrics of the cells in `only` (every shown cell when left out) and the links among them. */
export function sceneMetrics(s: SceneState, measure: Measure = estimateWidth, only?: Set<Node>): LayoutMetrics {
  const cells: MetricCell[] = [];
  const index = new Map<Node, number>();
  for (const n of s.nodes) {
    if (n.dying || !shown(n) || (only && !only.has(n))) continue;
    const x = n.tween ? n.tween.tx : n.x,
      y = n.tween ? n.tween.ty : n.y;
    const f = cellFootprint(n, measure);
    index.set(n, cells.length);
    cells.push({
      x,
      y,
      r: n.r,
      box: { x0: x - f.halfW, y0: y - f.up, x1: x + f.halfW, y1: y + f.down },
      group: n.domain ? `${n.domain.company.key}/${n.domain.key}` : null,
    });
  }
  const links: MetricLink[] = [];
  for (const l of s.links) {
    const a = index.get(l.a),
      b = index.get(l.b);
    if (a === undefined || b === undefined || a === b || l.dying) continue;
    links.push({ a, b, seed: l.seed, chipW: chipWidth(l, measure) });
  }
  return measureLayout(cells, links);
}
