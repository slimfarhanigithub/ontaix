/**
 * Readability metrics of the scene as it is drawn: every living, shown cell and the links
 * between them, at their positions (or at the end of their arrange tween).
 */
import { cellFootprint, chipWidth, estimateWidth, type Measure } from './footprint';
import { measureLayout, REGION_PAD, type LayoutMetrics, type MetricCell, type MetricHeader, type MetricLink } from './layoutMetrics';
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
  // Domain headers as `drawDomains` writes them: centred on the members' mean x, above the region.
  const headers: MetricHeader[] = [];
  for (const d of s.DOMAINS) {
    if (d.hidden) continue;
    const members = s.nodes.filter((n) => n.domain === d && !n.dying && index.has(n));
    if (!members.length) continue;
    const ys = members.map((n) => cells[index.get(n) as number].y);
    const cx = members.reduce((a, n) => a + cells[index.get(n) as number].x, 0) / members.length;
    const minY = Math.min(...ys);
    const pending = members.filter((n) => n.pending).length;
    const title = (s.companies.length > 1 ? d.company.name + ' · ' : '') + d.name.toUpperCase();
    const sub = `domain product · ${d.owner} · v${d.version.toFixed(1)} · ${members.length - pending} concepts${pending ? ` · ${pending} pending` : ''}`;
    const w = Math.max(measure(title, '500 12.5px Sora, sans-serif'), measure(sub, '300 10.5px Sora, sans-serif'));
    headers.push({
      group: `${d.company.key}/${d.key}`,
      box: { x0: cx - w / 2, y0: minY - REGION_PAD - 18 - 11, x1: cx + w / 2, y1: minY - REGION_PAD - 3 + 3 },
    });
  }
  return measureLayout(cells, links, headers);
}
