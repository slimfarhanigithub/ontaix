/**
 * A layered tree layout that reads from left to right, built for the way the canvas draws: a
 * link is a near-straight line between two cell centres with its action chip at the middle, and
 * a cell's labels hang under it.
 *
 * Every block is a tree: the birth tree of a company around its root, a lineage, a cell and its
 * neighbours, or a forest of tops side by side. Each tree level is a column; a column sits far
 * enough from the next for the widest labels of both and for every chip between them. Subtrees
 * are packed against each other column by column, a parent sits in the middle of its children,
 * so tree links never cross. A domain product's cells stay together under a parent, with extra
 * room where one domain meets another. The order of children is then chosen to keep the other
 * links (relations, equivalences) from crossing: barycentre sweeps, then a bounded local search
 * on the crossings that remain. Pure: no scene, no canvas, no clock.
 */
import { chipCorners, convexOverlap, linkShape } from './layoutMetrics';

export interface LayoutItem {
  id: number;
  r: number;
  /** Half the width of the cell and its labels. */
  halfW: number;
  /** Extent above the centre. */
  up: number;
  /** Extent below the centre, labels included. */
  down: number;
  /** Domain product of the cell; cells of one group stay together. */
  group: string | null;
}

export interface LayoutLink {
  a: number;
  b: number;
  /** Width of the action chip; 0 for a link without an action. */
  chipW: number;
  /** Curve bend of the link, as the renderer draws it. */
  seed: number;
}

export interface LayoutBlock {
  /** The item at the start of the tree, or null for a forest whose tops share the first column. */
  root: number | null;
  /** Tops of a rootless forest, in their starting order. */
  tops?: number[];
  /** Position of the root, or of the middle of the first column of a rootless forest. */
  at: [number, number];
  /** `both` splits the root's children between a left and a right side; `right` grows rightwards only. */
  sides: 'right' | 'both';
  /** Sides the caller fixes for some of the root's children. */
  side?: Map<number, -1 | 1>;
}

export interface LayoutInput {
  items: LayoutItem[];
  /** Tree parent of every item but the roots and tops. */
  parent: Map<number, number>;
  blocks: LayoutBlock[];
  /** Every drawn link among the items, tree links included. */
  links: LayoutLink[];
  /** Order of domain products among siblings; lower first. */
  groupRank?: (group: string | null) => number;
  /** Most layouts the local search may try. */
  budget?: number;
  /** Least horizontal room between the labels of two neighbouring blocks. */
  apart?: number;
}

export interface LayoutResult {
  pos: Map<number, [number, number]>;
  /** Straight-line crossings and links through cells of the result. */
  score: number;
}

/** Vertical room between two cells of one column. */
export const GAP_Y = 26;
/** Extra vertical room where two domain products meet in a column. */
export const GROUP_GAP = 64;
/** Horizontal room between the labels of two neighbouring columns. */
export const GAP_X = 36;
/** Room on each side of an action chip along its link. */
const CHIP_CLEAR = 12;
/** Shortest visible link length at which the renderer draws a chip, plus a margin. */
const CHIP_MIN_GAP = 76;
/** Rounds of chip-driven column widening. */
const WIDEN_ROUNDS = 24;
/** Barycentre sweeps before the local search. */
const SWEEPS = 4;

interface TN {
  id: number;
  item: LayoutItem | null;
  parent: TN | null;
  kids: TN[];
  depth: number;
  side: 1 | -1;
  block: number;
  /** Offset from the parent's y, written by the packer. */
  rel: number;
  x: number;
  y: number;
}

interface Contour {
  top: number[];
  bot: number[];
  topG: (string | null)[];
  botG: (string | null)[];
}

interface Edge {
  a: TN;
  b: TN;
  chipW: number;
  seed: number;
  tree: boolean;
}

/** Segments per link curve in the ordering measure. */
const SEARCH_STEPS = 6;

export function layoutForest(input: LayoutInput): LayoutResult {
  const L = new Layout(input);
  return L.run();
}

class Layout {
  private nodes = new Map<number, TN>();
  private heads: TN[] = [];
  private edges: Edge[] = [];
  private gaps: Map<string, number[]> = new Map();
  private rank: (g: string | null) => number;
  /** The link from a node to its tree parent. */
  private up = new Map<TN, Edge>();
  /** Extra room above a subtree, given where two chips met. */
  private extra = new Map<TN, number>();
  /** Widest chip of the other links between two cells, by `pairKey`. */
  private near = new Map<string, number>();

  constructor(private input: LayoutInput) {
    this.rank = input.groupRank ?? (() => 0);
    for (const it of input.items)
      this.nodes.set(it.id, { id: it.id, item: it, parent: null, kids: [], depth: 0, side: 1, block: -1, rel: 0, x: 0, y: 0 });
    input.blocks.forEach((b, bi) => {
      let head: TN;
      if (b.root !== null) head = this.nodes.get(b.root) as TN;
      else {
        head = { id: -1 - bi, item: null, parent: null, kids: [], depth: 0, side: 1, block: -1, rel: 0, x: 0, y: 0 };
        for (const t of b.tops ?? []) {
          const k = this.nodes.get(t);
          if (k) {
            k.parent = head;
            head.kids.push(k);
          }
        }
      }
      this.heads.push(head);
    });
    const order = new Map(input.items.map((it, i) => [it.id, i]));
    for (const it of input.items) {
      const p = input.parent.get(it.id);
      if (p === undefined) continue;
      const n = this.nodes.get(it.id) as TN,
        pn = this.nodes.get(p);
      if (!pn || pn === n) continue;
      n.parent = pn;
      pn.kids.push(n);
    }
    for (const n of this.nodes.values()) n.kids.sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
    for (const h of this.heads) h.block = this.heads.indexOf(h);
    for (const h of this.heads) this.claim(h, 0, h.block);
    for (const it of input.items) {
      const n = this.nodes.get(it.id) as TN;
      if (n.block !== -1) continue;
      // Not reachable from any block (a broken parent chain): it joins the first block's head.
      if (n.parent) n.parent.kids.splice(n.parent.kids.indexOf(n), 1);
      const h = this.heads[0];
      n.parent = h;
      h.kids.push(n);
      this.claim(n, 1, h.block);
    }
    for (const l of input.links) {
      const a = this.nodes.get(l.a),
        b = this.nodes.get(l.b);
      if (!a || !b || a === b) continue;
      const e: Edge = { a, b, chipW: l.chipW, seed: l.seed, tree: a.parent === b || b.parent === a };
      this.edges.push(e);
      if (e.tree) {
        const child = a.parent === b ? a : b;
        if (!this.up.has(child)) this.up.set(child, e);
      } else if (e.chipW) {
        const key = pairKey(a, b);
        this.near.set(key, Math.max(this.near.get(key) ?? 0, e.chipW));
      }
    }
    for (const h of this.heads) {
      for (const n of this.all(h)) n.kids.sort((a, b) => this.rank(a.item?.group ?? null) - this.rank(b.item?.group ?? null));
      this.assignSides(h);
    }
  }

  /** Walks a tree from its head, giving every node its depth and block; a node met twice stays with the first. */
  private claim(h: TN, depth: number, block: number): void {
    h.depth = depth;
    h.block = block;
    const stack = [h];
    while (stack.length) {
      const n = stack.pop() as TN;
      n.kids = n.kids.filter((k) => k.block === -1);
      for (const k of n.kids) {
        k.block = block;
        k.depth = n.depth + 1;
        stack.push(k);
      }
    }
  }

  private *all(h: TN): Generator<TN> {
    const stack = [h];
    while (stack.length) {
      const n = stack.pop() as TN;
      yield n;
      for (let i = n.kids.length - 1; i >= 0; i--) stack.push(n.kids[i]);
    }
  }

  private leaves(n: TN): number {
    let c = 0;
    for (const x of this.all(n)) if (!x.kids.length) c++;
    return c;
  }

  private setSide(n: TN, side: 1 | -1): void {
    for (const x of this.all(n)) x.side = side;
  }

  /** Splits a `both` root's children into two sides of about the same height, groups kept whole. */
  private assignSides(h: TN): void {
    const b = this.input.blocks[h.block];
    if (b.sides !== 'both' || !h.item) {
      for (const k of h.kids) this.setSide(k, 1);
      return;
    }
    const fixed = b.side ?? new Map<number, -1 | 1>();
    const weight = { [-1]: 0, [1]: 0 } as Record<number, number>;
    for (const k of h.kids)
      if (fixed.has(k.id)) {
        this.setSide(k, fixed.get(k.id) as 1 | -1);
        weight[k.side] += this.leaves(k);
      }
    const runs: TN[][] = [];
    for (const k of h.kids) {
      if (fixed.has(k.id)) continue;
      const last = runs[runs.length - 1];
      if (last && last[0].item?.group === k.item?.group) last.push(k);
      else runs.push([k]);
    }
    const wr = (run: TN[]) => run.reduce((a, k) => a + this.leaves(k), 0);
    runs.sort((p, q) => wr(q) - wr(p));
    for (const run of runs) {
      const side: 1 | -1 = weight[1] <= weight[-1] ? 1 : -1;
      for (const k of run) this.setSide(k, side);
      weight[side] += wr(run);
    }
    // Keep the starting group order on each side.
    const pos = new Map(h.kids.map((k, i) => [k, i]));
    h.kids.sort((p, q) => (pos.get(p) as number) - (pos.get(q) as number));
  }

  run(): LayoutResult {
    this.place();
    this.separate();
    let best = this.snapshot(),
      bestScore = this.score();
    for (let s = 0; s < SWEEPS && bestScore > 0; s++) {
      this.sweep();
      this.place();
      const sc = this.score();
      if (sc < bestScore) {
        bestScore = sc;
        best = this.snapshot();
      }
    }
    this.restore(best);
    this.place();
    bestScore = this.search(bestScore);
    this.place();
    this.widen();
    const pos = new Map<number, [number, number]>();
    for (const n of this.nodes.values()) pos.set(n.id, [n.x, n.y]);
    return { pos, score: bestScore };
  }

  private snapshot(): Map<TN, { kids: TN[]; side: 1 | -1 }> {
    const m = new Map<TN, { kids: TN[]; side: 1 | -1 }>();
    for (const h of this.heads) for (const n of this.all(h)) m.set(n, { kids: n.kids.slice(), side: n.side });
    return m;
  }

  private restore(m: Map<TN, { kids: TN[]; side: 1 | -1 }>): void {
    let moved = false;
    for (const [n, v] of m) {
      n.kids = v.kids.slice();
      if (n.side !== v.side) moved = true;
      n.side = v.side;
    }
    if (moved) this.gaps.clear();
  }

  /** Writes y (packing) and x (columns) of every node. */
  private place(): void {
    for (const h of this.heads) {
      const b = this.input.blocks[h.block];
      const sides: (1 | -1)[] = b.sides === 'both' && h.item ? [-1, 1] : [1];
      h.y = b.at[1];
      for (const side of sides) {
        const kids = h.kids.filter((k) => k.side === side || sides.length === 1);
        this.pack(h, kids);
        for (const k of kids) this.down(k, h.y);
      }
    }
    this.columns();
  }

  private down(n: TN, py: number): void {
    n.y = py + n.rel;
    for (const k of n.kids) this.down(k, n.y);
  }

  private own(n: TN): Contour {
    if (!n.item) return { top: [NaN], bot: [NaN], topG: [null], botG: [null] };
    const g = n.item.group;
    return { top: [-n.item.up], bot: [n.item.down], topG: [g], botG: [g] };
  }

  /** Packs the subtrees of `kids` one under another, as close as their columns allow. */
  private pack(n: TN, kids: TN[]): Contour {
    const own = this.own(n);
    if (!kids.length) return own;
    let acc: Contour | null = null;
    const offs: number[] = [];
    for (let i = 0; i < kids.length; i++) {
      const k = kids[i];
      const ck = this.pack(k, k.kids);
      if (!acc) {
        offs.push(0);
        acc = ck;
        continue;
      }
      let off = -Infinity;
      const m = Math.min(acc.bot.length, ck.top.length);
      for (let d = 0; d < m; d++) {
        if (Number.isNaN(acc.bot[d]) || Number.isNaN(ck.top[d])) continue;
        const sep = GAP_Y + (acc.botG[d] !== ck.topG[d] ? GROUP_GAP : 0);
        off = Math.max(off, acc.bot[d] + sep - ck.top[d]);
      }
      if (off === -Infinity) off = 0;
      const prev = kids[i - 1];
      const chip = this.near.get(pairKey(prev, k));
      // A labelled link between two neighbours runs straight down from one to the other; its chip
      // sits half-way, so the half-way point must clear the upper one's labels by half a chip.
      if (chip && prev.item && k.item)
        off = Math.max(off, offs[i - 1] + 2 * Math.max(prev.item.down, k.item.up) + chip + 2 * CHIP_CLEAR);
      off += this.extra.get(k) ?? 0;
      offs.push(off);
      const merged: Contour = { top: [], bot: [], topG: [], botG: [] };
      const len = Math.max(acc.top.length, ck.top.length);
      for (let d = 0; d < len; d++) {
        const ha = d < acc.top.length && !Number.isNaN(acc.top[d]),
          hb = d < ck.top.length && !Number.isNaN(ck.top[d]);
        merged.top.push(ha ? acc.top[d] : hb ? ck.top[d] + off : NaN);
        merged.topG.push(ha ? acc.topG[d] : hb ? ck.topG[d] : null);
        merged.bot.push(hb ? ck.bot[d] + off : ha ? acc.bot[d] : NaN);
        merged.botG.push(hb ? ck.botG[d] : ha ? acc.botG[d] : null);
      }
      acc = merged;
    }
    const mid = (offs[0] + offs[offs.length - 1]) / 2;
    kids.forEach((k, i) => (k.rel = offs[i] - mid));
    const a = acc as Contour;
    return {
      top: [own.top[0], ...a.top.map((v) => v - mid)],
      bot: [own.bot[0], ...a.bot.map((v) => v - mid)],
      topG: [own.topG[0], ...a.topG],
      botG: [own.botG[0], ...a.botG],
    };
  }

  private key(n: TN): string {
    return `${n.block}:${n.side}`;
  }

  /** Column distances of every block side, from the labels and chips between neighbouring columns. */
  private columns(): void {
    const cols = new Map<string, TN[][]>();
    for (const h of this.heads)
      for (const n of this.all(h)) {
        if (n === h && this.input.blocks[h.block].sides === 'both') {
          for (const side of [-1, 1] as const) this.col(cols, `${n.block}:${side}`, 0).push(n);
          continue;
        }
        this.col(cols, this.key(n), n.depth).push(n);
      }
    for (const [key, layers] of cols) {
      let gaps = this.gaps.get(key);
      if (!gaps) {
        gaps = [0];
        for (let d = 1; d < layers.length; d++) {
          const prev = layers[d - 1].filter((n) => n.item),
            cur = layers[d];
          let g = 0;
          const hw = (ns: TN[]) => ns.reduce((a, n) => Math.max(a, n.item ? n.item.halfW : 0), 0);
          if (prev.length) g = hw(prev) + hw(cur) + GAP_X;
          for (const n of cur) {
            if (!n.parent || !n.parent.item || !n.item) continue;
            const e = this.up.get(n);
            const chip = e && e.chipW ? e.chipW + 2 * CHIP_CLEAR : 0;
            g = Math.max(g, n.item.r * 1.05 + n.parent.item.r * 1.05 + 10 + Math.max(chip, CHIP_MIN_GAP));
          }
          gaps.push(g);
        }
        this.gaps.set(key, gaps);
      }
      while (gaps.length < layers.length) gaps.push(gaps[gaps.length - 1] || 200);
      const [blockS, sideS] = key.split(':');
      const b = this.input.blocks[Number(blockS)],
        side = Number(sideS) as 1 | -1;
      const rootless = b.root === null;
      let x = b.at[0];
      for (let d = 0; d < layers.length; d++) {
        if (d > 0 && !(rootless && d === 1)) x += side * gaps[d];
        for (const n of layers[d]) n.x = x;
      }
    }
  }

  private col(cols: Map<string, TN[][]>, key: string, d: number): TN[] {
    let layers = cols.get(key);
    if (!layers) cols.set(key, (layers = []));
    while (layers.length <= d) layers.push([]);
    return layers[d];
  }

  /** Leftmost and rightmost label edge of a block's two sides, measured from its root. */
  private extent(h: TN, side: 1 | -1): number {
    let m = h.item ? h.item.halfW : 0;
    for (const k of h.kids)
      if (k.side === side) for (const n of this.all(k)) m = Math.max(m, side * (n.x - h.x) + (n.item ? n.item.halfW : 0));
    return m;
  }

  /** Neighbouring blocks (left to right) whose facing sides come closer than `apart`. */
  private clash(): [TN, TN] | null {
    const apart = this.input.apart;
    if (apart === undefined) return null;
    const hs = this.heads.filter((h) => h.item).sort((p, q) => p.x - q.x);
    for (let i = 0; i + 1 < hs.length; i++) {
      const a = hs[i],
        b = hs[i + 1];
      if (this.extent(a, 1) + this.extent(b, -1) + apart > b.x - a.x) return [a, b];
    }
    return null;
  }

  /** Moves subtrees off the facing sides of neighbouring blocks until they keep apart. */
  private separate(): void {
    for (let guard = 0; guard < this.nodes.size; guard++) {
      const pair = this.clash();
      if (!pair) return;
      const [a, b] = pair;
      const movable = (h: TN, side: 1 | -1) => {
        const blk = this.input.blocks[h.block];
        return blk.sides === 'both' ? h.kids.filter((k) => k.side === side && !blk.side?.has(k.id)) : [];
      };
      const ka = movable(a, 1),
        kb = movable(b, -1);
      if (!ka.length && !kb.length) return;
      // The side that reaches less gives way, so the deeper tree keeps its room.
      const fromA = kb.length === 0 || (ka.length > 0 && this.extent(a, 1) <= this.extent(b, -1));
      const h = fromA ? a : b,
        cand = fromA ? ka : kb,
        to: 1 | -1 = fromA ? -1 : 1;
      const reach = (k: TN) => {
        let m = 0;
        for (const n of this.all(k)) m = Math.max(m, Math.abs(n.x - h.x));
        return m;
      };
      cand.sort((p, q) => reach(q) - reach(p));
      this.setSide(cand[0], to);
      this.gaps.clear();
      this.place();
    }
  }

  /** Lowest common ancestor walk: adds `y` to the pull of every node from `n` up to below `stop`. */
  private pullUp(n: TN, stop: TN | null, y: number, pull: Map<TN, number[]>): void {
    let c: TN | null = n;
    while (c && c !== stop && c.parent) {
      const p = pull.get(c);
      if (p) p.push(y);
      else pull.set(c, [y]);
      c = c.parent;
    }
  }

  private lca(a: TN, b: TN): TN | null {
    if (a.block !== b.block) return null;
    let x: TN | null = a,
      y: TN | null = b;
    while (x && y && x.depth > y.depth) x = x.parent;
    while (x && y && y.depth > x.depth) y = y.parent;
    while (x && y && x !== y) {
      x = x.parent;
      y = y.parent;
    }
    return x;
  }

  /** One barycentre sweep: children follow the y of what their subtrees link to. */
  private sweep(): void {
    const pull = new Map<TN, number[]>();
    for (const e of this.edges) {
      if (e.tree) continue;
      const anc = this.lca(e.a, e.b);
      this.pullUp(e.a, anc, e.b.y, pull);
      this.pullUp(e.b, anc, e.a.y, pull);
    }
    const key = (k: TN) => {
      const p = pull.get(k);
      return p ? p.reduce((a, v) => a + v, 0) / p.length : k.y;
    };
    for (const h of this.heads)
      for (const n of this.all(h)) {
        if (n.kids.length < 2) continue;
        const keys = new Map(n.kids.map((k) => [k, key(k)]));
        const groups = new Map<string, TN[]>();
        for (const k of n.kids) {
          const g = `${k.side}|${k.item?.group ?? ''}`;
          const list = groups.get(g);
          if (list) list.push(k);
          else groups.set(g, [k]);
        }
        const gk = (list: TN[]) => list.reduce((a, k) => a + (keys.get(k) as number), 0) / list.length;
        const ordered = [...groups.values()].sort((p, q) => gk(p) - gk(q));
        n.kids = ordered.flatMap((list) => list.sort((p, q) => (keys.get(p) as number) - (keys.get(q) as number)));
      }
  }

  /** Straight-line crossings plus links through cells; the measure the ordering minimises. */
  private score(): number {
    return this.problems(1).length;
  }

  /** Every crossing pair and every link through a cell, as the nodes involved. */
  private problems(steps = SEARCH_STEPS): TN[][] {
    const segs = this.edges.map((e) => {
      const pts = linkShape(this.geo(e.a), this.geo(e.b), e.seed, steps).pts;
      let x0 = Infinity,
        y0 = Infinity,
        x1 = -Infinity,
        y1 = -Infinity;
      for (const [x, y] of pts) {
        x0 = Math.min(x0, x);
        y0 = Math.min(y0, y);
        x1 = Math.max(x1, x);
        y1 = Math.max(y1, y);
      }
      return { e, pts, x0, y0, x1, y1 };
    });
    const out: TN[][] = [];
    const order = segs.map((_, i) => i).sort((i, j) => segs[i].x0 - segs[j].x0);
    for (let oi = 0; oi < order.length; oi++) {
      const s = segs[order[oi]];
      for (let oj = oi + 1; oj < order.length; oj++) {
        const t = segs[order[oj]];
        if (t.x0 > s.x1) break;
        if (t.y0 > s.y1 || s.y0 > t.y1) continue;
        if (s.e.a === t.e.a || s.e.a === t.e.b || s.e.b === t.e.a || s.e.b === t.e.b) continue;
        if (polyCross(s.pts, t.pts)) out.push([s.e.a, s.e.b, t.e.a, t.e.b]);
      }
    }
    const cells = [...this.nodes.values()].filter((n) => n.item);
    const left = (n: TN) => n.x - (n.item as LayoutItem).halfW;
    cells.sort((p, q) => left(p) - left(q));
    const xs = cells.map(left);
    let widest = 0;
    for (const c of cells) widest = Math.max(widest, 2 * (c.item as LayoutItem).halfW);
    for (const s of segs) {
      let lo = 0,
        hi = cells.length;
      const from = s.x0 - widest;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (xs[mid] < from) lo = mid + 1;
        else hi = mid;
      }
      for (let i = lo; i < cells.length && xs[i] <= s.x1; i++) {
        const c = cells[i],
          it = c.item as LayoutItem;
        if (c === s.e.a || c === s.e.b || c.x + it.halfW < s.x0) continue;
        if (c.y - it.up > s.y1 || c.y + it.down < s.y0) continue;
        for (let k = 0; k + 1 < s.pts.length; k++) {
          const [p, q] = [s.pts[k], s.pts[k + 1]];
          if (
            distToSeg(c.x, c.y, p[0], p[1], q[0], q[1]) < it.r + 2 ||
            segBox(p[0], p[1], q[0], q[1], c.x - it.halfW, c.y + it.r + 10, c.x + it.halfW, c.y + it.down)
          ) {
            out.push([s.e.a, s.e.b, c]);
            break;
          }
        }
      }
    }
    return out;
  }

  private geo(n: TN): { x: number; y: number; r: number } {
    return { x: n.x, y: n.y, r: n.item ? n.item.r : 0 };
  }

  /** Bounded local search over sibling order and root sides, driven by the remaining problems. */
  private search(start: number): number {
    let best = start;
    const budget = this.input.budget ?? 160;
    let evals = 0;
    let improved = true;
    while (best > 0 && improved && evals < budget) {
      improved = false;
      const involved = new Set<TN>();
      for (const p of this.problems(1)) for (const n of p) for (let c: TN | null = n; c && c.parent; c = c.parent) involved.add(c);
      const parents = new Set<TN>();
      for (const n of involved) if (n.parent) parents.add(n.parent);
      for (const p of parents) {
        for (const move of this.moves(p, involved)) {
          if (evals >= budget) break;
          const snap = this.snapshot();
          move();
          this.place();
          evals++;
          const sc = this.clash() ? Infinity : this.score();
          if (sc < best) {
            best = sc;
            improved = true;
            break;
          }
          this.restore(snap);
        }
        if (improved || evals >= budget) break;
      }
    }
    this.place();
    return best;
  }

  /**
   * Candidate changes at a parent: swap a child with a neighbour of its group, swap its group's
   * run with the next run, mirror the children, or move a root's child to the root's other side.
   */
  private moves(p: TN, involved: Set<TN>): (() => void)[] {
    const out: (() => void)[] = [];
    const kids = p.kids;
    const g = (n: TN) => n.item?.group ?? null;
    const runOf = (i: number): [number, number] => {
      let a = i,
        b = i;
      while (a > 0 && g(kids[a - 1]) === g(kids[i]) && kids[a - 1].side === kids[i].side) a--;
      while (b + 1 < kids.length && g(kids[b + 1]) === g(kids[i]) && kids[b + 1].side === kids[i].side) b++;
      return [a, b];
    };
    const blk = this.input.blocks[p.block];
    for (let i = 0; i < kids.length; i++) {
      if (!involved.has(kids[i])) continue;
      for (const j of [i - 1, i + 1]) {
        if (j < 0 || j >= kids.length || kids[j].side !== kids[i].side || g(kids[j]) !== g(kids[i])) continue;
        out.push(() => {
          [p.kids[i], p.kids[j]] = [p.kids[j], p.kids[i]];
        });
      }
      const [a, b] = runOf(i);
      if (a > 0 && kids[a - 1].side === kids[i].side) {
        const [pa] = runOf(a - 1);
        out.push(() => {
          const prev = p.kids.slice(pa, a),
            cur = p.kids.slice(a, b + 1);
          p.kids.splice(pa, b + 1 - pa, ...cur, ...prev);
        });
      }
      if (b + 1 < kids.length && kids[b + 1].side === kids[i].side) {
        const [, nb] = runOf(b + 1);
        out.push(() => {
          const cur = p.kids.slice(a, b + 1),
            next = p.kids.slice(b + 1, nb + 1);
          p.kids.splice(a, nb + 1 - a, ...next, ...cur);
        });
      }
      if (!p.parent && p.item && blk.sides === 'both' && !blk.side?.has(kids[i].id)) {
        const k = kids[i];
        const to = (-k.side) as 1 | -1;
        const others = kids.filter((x) => x.side === to);
        for (let at = 0; at <= others.length; at++)
          out.push(() => {
            p.kids.splice(p.kids.indexOf(k), 1);
            const before = others[at];
            if (before) p.kids.splice(p.kids.indexOf(before), 0, k);
            else p.kids.push(k);
            this.setSide(k, to);
            this.gaps.clear();
          });
      }
    }
    if (kids.length > 1)
      out.push(() => {
        p.kids.reverse();
      });
    return out;
  }

  /**
   * Makes room for every chip that still covers a cell or another chip: two chips that meet push
   * the lower subtree down; a chip on a cell, or one with no room on its link, widens its column.
   */
  private widen(): void {
    for (let round = 0; round < WIDEN_ROUNDS; round++) {
      const { wide, tall } = this.chipConflicts();
      if (!wide.size && !tall.size) return;
      for (const n of tall) {
        // The room goes above the nearest subtree, from `n` up, that has a sibling above it.
        let t: TN | null = n;
        while (t && t.parent && t.parent.kids.find((k) => k.side === t!.side) === t) t = t.parent;
        if (t && t.parent) this.extra.set(t, (this.extra.get(t) ?? 0) + 24);
      }
      const cols = new Set<string>();
      for (const n of wide) cols.add(`${this.key(n)}#${n.depth}`);
      for (const c of cols) {
        const [key, d] = c.split('#');
        const gaps = this.gaps.get(key),
          depth = Number(d);
        if (gaps && depth > 0 && depth < gaps.length) gaps[depth] = gaps[depth] * 1.12 + 8;
      }
      this.place();
    }
  }

  /**
   * Children whose tree link carries a chip that covers a cell or has no room (`wide`), and the
   * lower child of two whose chips meet (`tall`).
   */
  private chipConflicts(): { wide: Set<TN>; tall: Set<TN> } {
    // `n` is the child of a tree link, null for another link; `ends` are the link's two cells.
    type Chip = { n: TN | null; ends: TN[]; poly: [number, number][]; x0: number; x1: number; y0: number; y1: number };
    const chips: Chip[] = [];
    const bad = new Set<TN>(),
      tall = new Set<TN>();
    for (const e of this.edges) {
      if (!e.chipW || !e.a.item || !e.b.item) continue;
      const sh = linkShape(this.geo(e.a), this.geo(e.b), e.seed);
      const child = e.tree ? (e.a.parent === e.b ? e.a : e.b) : null;
      if (!sh.chip || sh.gap < e.chipW + 2 * CHIP_CLEAR) {
        if (child) bad.add(child);
        continue;
      }
      const poly = chipCorners(sh.chip.x, sh.chip.y, sh.chip.ang, e.chipW + 4, 22);
      const xs = poly.map((p) => p[0]),
        ys = poly.map((p) => p[1]);
      chips.push({ n: child, ends: [e.a, e.b], poly, x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) });
    }
    const cells = [...this.nodes.values()].filter((n) => n.item);
    const left = (n: TN) => n.x - (n.item as LayoutItem).halfW;
    cells.sort((p, q) => left(p) - left(q));
    const xs = cells.map(left);
    let widest = 0;
    for (const c of cells) widest = Math.max(widest, 2 * (c.item as LayoutItem).halfW);
    chips.sort((p, q) => p.x0 - q.x0);
    for (let i = 0; i < chips.length; i++) {
      const a = chips[i];
      let lo = 0,
        hi = cells.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (xs[mid] < a.x0 - widest) lo = mid + 1;
        else hi = mid;
      }
      for (let ci = lo; ci < cells.length && xs[ci] < a.x1; ci++) {
        const c = cells[ci],
          it = c.item as LayoutItem;
        const parts: [number, number, number, number][] = [
          [c.x - it.r - 2, c.y - it.up, c.x + it.r + 2, c.y + it.r + 2],
          [c.x - it.halfW, c.y + it.r + 10, c.x + it.halfW, c.y + it.down],
        ];
        for (const [x0, y0, x1, y1] of parts) {
          if (a.x1 <= x0 || x1 <= a.x0 || a.y1 <= y0 || y1 <= a.y0) continue;
          if (
            convexOverlap(a.poly, [
              [x0, y0],
              [x1, y0],
              [x1, y1],
              [x0, y1],
            ])
          ) {
            if (a.n) {
              bad.add(a.n);
              if (c.parent && c !== a.n && c !== a.n.parent) bad.add(c);
            } else if (!a.ends.includes(c)) tall.add(c);
          }
        }
      }
      for (let j = i + 1; j < chips.length; j++) {
        const b = chips[j];
        if (b.x0 >= a.x1) break;
        if (a.y1 <= b.y0 || b.y1 <= a.y0) continue;
        if (!convexOverlap(a.poly, b.poly) || a.n === b.n) continue;
        if (a.n && b.n) tall.add(a.n.y > b.n.y ? a.n : b.n);
        else if (a.n || b.n) tall.add((a.n ?? b.n) as TN);
      }
    }
    return { wide: bad, tall };
  }
}

const pairKey = (a: TN, b: TN): string => (a.id < b.id ? `${a.id}:${b.id}` : `${b.id}:${a.id}`);

function polyCross(p: [number, number][], q: [number, number][]): boolean {
  for (let i = 0; i + 1 < p.length; i++)
    for (let j = 0; j + 1 < q.length; j++)
      if (cross(p[i][0], p[i][1], p[i + 1][0], p[i + 1][1], q[j][0], q[j][1], q[j + 1][0], q[j + 1][1])) return true;
  return false;
}

function cross(ax: number, ay: number, bx: number, by: number, cx: number, cy: number, dx: number, dy: number): boolean {
  const o = (px: number, py: number, qx: number, qy: number, rx: number, ry: number) =>
    (qx - px) * (ry - py) - (qy - py) * (rx - px);
  const d1 = o(cx, cy, dx, dy, ax, ay),
    d2 = o(cx, cy, dx, dy, bx, by),
    d3 = o(ax, ay, bx, by, cx, cy),
    d4 = o(ax, ay, bx, by, dx, dy);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

function distToSeg(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax,
    dy = by - ay,
    l2 = dx * dx + dy * dy;
  const u = l2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2)) : 0;
  return Math.hypot(px - (ax + dx * u), py - (ay + dy * u));
}

function segBox(ax: number, ay: number, bx: number, by: number, x0: number, y0: number, x1: number, y1: number): boolean {
  let t0 = 0,
    t1 = 1;
  const dx = bx - ax,
    dy = by - ay;
  for (const [den, num] of [
    [-dx, ax - x1],
    [dx, x0 - ax],
    [-dy, ay - y1],
    [dy, y0 - ay],
  ]) {
    if (den === 0) {
      if (num > 0) return false;
      continue;
    }
    const t = num / den;
    if (den > 0) {
      if (t > t1) return false;
      if (t > t0) t0 = t;
    } else {
      if (t < t0) return false;
      if (t < t1) t1 = t;
    }
  }
  return t0 <= t1;
}
