/**
 * Whole-model layout as one tree per company with every domain product kept in one region.
 *
 * Each domain product's cells form one block: the cells whose birth parent lies in another
 * domain product (its tops) all hang from one cell, the parent of the largest of them, so a
 * domain product never splits across the model. The tree is laid out by `layered.ts`, read away
 * from each company root on both sides, with room between groups for their tinted regions and
 * headers. When a block still comes too close to another one's region (it hangs from a cell in
 * the middle of that region), it moves to start one empty column after that region's last
 * column, its link passing under the cells it skips, and the tree is laid out again.
 */
import { cellFootprint, chipWidth, type Measure } from './footprint';
import { hull, type Pt } from './hulls';
import { layoutForest, type LayoutBlock, type LayoutItem, type LayoutLink } from './layered';
import { REGION_PAD, regionDistance } from './layoutMetrics';
import type { SceneState } from './state';
import type { Company, Node } from './types';

/** Least room between two companies' trees. */
export const COMPANY_CLEAR = 420;
/**
 * Vertical room, beyond the label gap, between two blocks in one column: the lower region's
 * header and both regions' 86 px tint.
 */
const BLOCK_GAP_Y = 150;
/** Horizontal room between two columns where a link passes from one block to another. */
const BLOCK_GAP_X = 120;
/** Room kept between two regions, and between a header and another region, beyond the tint. */
const REGION_CLEAR = 24;
/** Most times the tree is laid out again to move blocks out of another block's region; once above 150 cells. */
const ROUNDS = 3;

/** Positions of every living, non-root cell of `companies`; the roots stay where they are. */
export function layoutByDomain(s: SceneState, companies: Company[], measure: Measure): Map<Node, [number, number]> {
  const roots = new Map(companies.map((c) => [c, c.root as Node]));
  const cells = s.nodes.filter((n) => !n.dying && !n.fixed && n.company && roots.has(n.company));
  const cellSet = new Set(cells);
  const boundTo = new Map<Node, Node>();
  for (const n of cells)
    if (n.kind === 'source') {
      const l = s.links.find(
        (x) => x.kind === 'bind' && x.a === n && !x.dying && cellSet.has(x.b) && x.b.company === n.company && x.b.kind !== 'source',
      );
      if (l) boundTo.set(n, l.b);
    }
  /** Birth parent (a source: its first bound concept) inside the same company, or null for the root. */
  const birth = (n: Node): Node | null => {
    const b = boundTo.get(n);
    if (b) return b;
    return n.parent && cellSet.has(n.parent) && n.parent.company === n.company ? n.parent : null;
  };
  const keyOf = (n: Node): string => {
    const b = boundTo.get(n);
    if (b) return keyOf(b);
    return `${(n.company as Company).key}/${n.domain ? n.domain.key : '-'}`;
  };
  const blockOf = new Map<Node, string>();
  const members = new Map<string, Node[]>();
  for (const n of cells) {
    const k = keyOf(n);
    blockOf.set(n, k);
    members.set(k, [...(members.get(k) ?? []), n]);
  }
  const inner = (n: Node): Node | null => {
    const p = birth(n);
    return p && blockOf.get(p) === blockOf.get(n) ? p : null;
  };
  const kids = new Map<Node, Node[]>();
  for (const n of cells) {
    const p = inner(n);
    if (p) kids.set(p, [...(kids.get(p) ?? []), n]);
  }
  const size = (n: Node, guard = 0): number =>
    guard > 200 ? 1 : 1 + (kids.get(n) ?? []).reduce((a, k) => a + size(k, guard + 1), 0);

  // Every block hangs from one cell (or its company root): the parent of its largest top.
  const parent = new Map<number, number>();
  const tops = new Map<string, Node[]>();
  for (const [k, ns] of members) {
    const ts = ns.filter((n) => !inner(n));
    ts.sort((p, q) => size(q) - size(p) || p.id - q.id);
    tops.set(k, ts);
    const from = ts.length ? birth(ts[0]) : null;
    const root = roots.get(ns[0].company as Company) as Node;
    for (const n of ns) {
      const p = inner(n);
      parent.set(n.id, p ? p.id : from ? from.id : root.id);
    }
  }
  const byId = new Map(cells.map((n) => [n.id, n]));
  const skip = new Map<number, number>();
  const depth = (n: Node, guard = 0): number => {
    const p = byId.get(parent.get(n.id) as number);
    return (p && guard < cells.length ? depth(p, guard + 1) : 0) + 1 + (skip.get(n.id) ?? 0);
  };
  const depthOfBlock = (k: string): number => Math.min(...(members.get(k) as Node[]).map((n) => depth(n)));

  const items: LayoutItem[] = [];
  for (const c of companies) items.push(itemOf(roots.get(c) as Node, measure, null));
  for (const n of cells) items.push(itemOf(n, measure, blockOf.get(n) as string));
  const blocks: LayoutBlock[] = companies.map((c) => ({ root: (roots.get(c) as Node).id, at: [c.x, c.y], sides: 'both' }));
  const all = new Set<Node>([...cells, ...roots.values()]);
  const links: LayoutLink[] = [];
  for (const l of s.links)
    if (!l.dying && l.a !== l.b && all.has(l.a) && all.has(l.b))
      links.push({ a: l.a.id, b: l.b.id, chipW: chipWidth(l, measure), seed: l.seed });
  const rank = new Map<string, number>();
  s.companies.forEach((c, ci) => c.domains.forEach((d) => rank.set(`${c.key}/${d.key}`, ci * 1000 + d.position)));

  // Large models check regions on a draft (no local search, no chip room), then lay out once in full.
  const big = cells.length > 150;
  const rounds = big ? 1 : ROUNDS;
  const lay = (draft: boolean) =>
    layoutForest({
      items,
      parent,
      blocks,
      links,
      skip,
      groupGap: BLOCK_GAP_Y,
      groupGapX: BLOCK_GAP_X,
      apart: COMPANY_CLEAR,
      groupRank: (g) => (g === null ? -1 : (rank.get(g) ?? 999)),
      budget: cells.length > 200 ? 25 : cells.length > 100 ? 50 : 300,
      draft,
    }).pos;
  let pos = lay(big);
  for (let round = 0; round < rounds; round++) {
    const clash = crowded(members, pos, measure, s.companies.length > 1);
    let moved = false;
    for (const [a, b] of clash) {
      // The block that hangs from a cell of the other moves out; between two others, the deeper one.
      const hangs = (x: string, y: string) => {
        const p = byId.get(parent.get((tops.get(x) as Node[])[0].id) as number);
        return !!p && blockOf.get(p) === y;
      };
      const [move, stay] = hangs(a, b) ? [a, b] : hangs(b, a) ? [b, a] : depthOfBlock(a) >= depthOfBlock(b) ? [a, b] : [b, a];
      const last = Math.max(...(members.get(stay) as Node[]).map((n) => depth(n)));
      for (const t of tops.get(move) as Node[]) {
        const want = (skip.get(t.id) ?? 0) + Math.max(0, last + 2 - depth(t));
        if (want > (skip.get(t.id) ?? 0)) {
          skip.set(t.id, want);
          moved = true;
        }
      }
    }
    if (!moved) break;
    pos = lay(big && round + 1 < rounds);
  }
  if (big) pos = lay(false);
  const out = new Map<Node, [number, number]>();
  for (const n of cells) out.set(n, pos.get(n.id) as [number, number]);
  return out;
}

/**
 * Pairs of blocks whose tinted regions come too close, or where one block's header comes too
 * close to another's region.
 */
function crowded(
  members: Map<string, Node[]>,
  pos: Map<number, [number, number]>,
  measure: Measure,
  multi: boolean,
): [string, string][] {
  const regions: { key: string; hull: Pt[]; header: Pt[] }[] = [];
  for (const [key, ns] of members) {
    const domainCells = ns.filter((n) => n.domain && n.kind !== 'source');
    if (!domainCells.length) continue;
    const pts = domainCells.map((n) => pos.get(n.id) as Pt);
    const d = domainCells[0].domain!;
    const title = (multi ? `${d.company.name} · ` : '') + d.name.toUpperCase();
    const sub = `domain product · ${d.owner} · v${d.version.toFixed(1)} · ${domainCells.length} concepts · 99 pending`;
    const w = Math.max(measure(title, '500 12.5px Sora, sans-serif'), measure(sub, '300 10.5px Sora, sans-serif')) / 2;
    const cx = pts.reduce((a, p) => a + p[0], 0) / pts.length;
    const top = Math.min(...pts.map((p) => p[1])) - REGION_PAD;
    regions.push({
      key,
      hull: hull(pts),
      header: [
        [cx - w, top - 29],
        [cx + w, top - 29],
        [cx + w, top],
        [cx - w, top],
      ],
    });
  }
  const out: [string, string][] = [];
  for (let i = 0; i < regions.length; i++)
    for (let j = i + 1; j < regions.length; j++) {
      const a = regions[i],
        b = regions[j];
      if (
        regionDistance(a.hull, b.hull) < 2 * REGION_PAD + REGION_CLEAR ||
        regionDistance(a.header, b.hull) < REGION_PAD + REGION_CLEAR ||
        regionDistance(b.header, a.hull) < REGION_PAD + REGION_CLEAR
      )
        out.push([a.key, b.key]);
    }
  return out;
}

function itemOf(n: Node, measure: Measure, group: string | null): LayoutItem {
  const f = cellFootprint(n, measure);
  return { id: n.id, r: Math.max(n.r, n.rt), halfW: f.halfW, up: f.up, down: f.down, group };
}
