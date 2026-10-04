import { mulberry32 } from '../runtime/mulberry32';
import { estimateWidth } from './footprint';
import { layoutForest, type LayoutBlock, type LayoutItem, type LayoutLink } from './layered';
import { measureLayout, type MetricCell, type MetricLink } from './layoutMetrics';

const ACTIONS = ['has', 'is planned by', 'records', 'belongs to', 'checked against'];

/** A seeded random tree: labels and actions of varied length, a domain kept three times in four. */
function tree(size: number, seed: number) {
  const rnd = mulberry32(seed);
  const items: LayoutItem[] = [];
  const parent = new Map<number, number>();
  const links: LayoutLink[] = [];
  const groups = ['a', 'b', 'c', 'd'];
  for (let i = 0; i < size; i++) {
    const label = `Concept ${'x'.repeat(Math.floor(rnd() * 14))} ${i}`;
    const w = estimateWidth(label, '600 13px Sora');
    const p = i ? Math.floor(Math.pow(rnd(), 0.6) * i) : -1;
    const group = p >= 0 && rnd() < 0.75 ? (items[p].group as string) : groups[Math.floor(rnd() * groups.length)];
    items.push({ id: i, r: 24, halfW: Math.max(28, w / 2 + 4), up: 28, down: 24 + 29 + 14, group });
    if (p >= 0) {
      parent.set(i, p);
      const action = ACTIONS[Math.floor(rnd() * ACTIONS.length)];
      links.push({ a: p, b: i, chipW: estimateWidth(action, '500 10.5px Sora') + 16, seed: rnd() });
    }
  }
  return { items, parent, links };
}

function metrics(items: LayoutItem[], links: LayoutLink[], pos: Map<number, [number, number]>) {
  const index = new Map(items.map((it, i) => [it.id, i]));
  const cells: MetricCell[] = items.map((it) => {
    const [x, y] = pos.get(it.id) as [number, number];
    return { x, y, r: it.r, box: { x0: x - it.halfW, y0: y - it.up, x1: x + it.halfW, y1: y + it.down }, group: it.group };
  });
  const ml: MetricLink[] = links.map((l) => ({ a: index.get(l.a)!, b: index.get(l.b)!, seed: l.seed, chipW: l.chipW }));
  return measureLayout(cells, ml);
}

describe('layered tree layout', () => {
  for (const [size, seed, sides] of [
    [12, 1, 'right'],
    [40, 2, 'both'],
    [90, 3, 'right'],
    [160, 4, 'both'],
  ] as const) {
    it(`lays a ${size}-cell tree (${sides}) out with no crossing, overlap or hidden action`, () => {
      const { items, parent, links } = tree(size, seed);
      const block: LayoutBlock = { root: 0, at: [100, 50], sides };
      const { pos } = layoutForest({ items, parent, blocks: [block], links });
      const m = metrics(items, links, pos);
      expect(m).toMatchObject({ crossings: 0, cellOverlaps: 0, chipOverlaps: 0, chipsOnCells: 0, hiddenLabels: 0 });
      expect(pos.get(0)).toEqual([100, 50]);
      for (const [c, p] of parent) {
        const [cx] = pos.get(c)!,
          [px] = pos.get(p)!;
        expect(Math.abs(cx - px)).toBeGreaterThan(0);
        if (sides === 'right') expect(cx).toBeGreaterThan(px);
      }
    });
  }

  it('puts a parent between its first and last child', () => {
    const { items, parent, links } = tree(30, 9);
    const { pos } = layoutForest({ items, parent, blocks: [{ root: 0, at: [0, 0], sides: 'right' }], links });
    const kids = new Map<number, number[]>();
    for (const [c, p] of parent) kids.set(p, [...(kids.get(p) ?? []), c]);
    for (const [p, ks] of kids) {
      const ys = ks.map((k) => pos.get(k)![1]);
      const y = pos.get(p)![1];
      expect(y).toBeGreaterThanOrEqual(Math.min(...ys) - 1e-6);
      expect(y).toBeLessThanOrEqual(Math.max(...ys) + 1e-6);
    }
  });

  it('starts every top of a rootless forest in one column', () => {
    const { items, parent, links } = tree(20, 5);
    const tops = [...parent].filter(([, p]) => p === 0).map(([c]) => c);
    for (const t of tops) parent.delete(t);
    const rest = items.filter((it) => it.id !== 0);
    const { pos } = layoutForest({
      items: rest,
      parent,
      blocks: [{ root: null, tops, at: [300, 0], sides: 'right' }],
      links: links.filter((l) => l.a !== 0),
    });
    for (const t of tops) expect(pos.get(t)![0]).toBe(300);
  });

  it('leaves room for the action of a link between two neighbours of one column', () => {
    const items: LayoutItem[] = [0, 1, 2].map((id) => ({ id, r: 24, halfW: 40, up: 28, down: 67, group: null }));
    const parent = new Map([
      [1, 0],
      [2, 0],
    ]);
    const links: LayoutLink[] = [
      { a: 0, b: 1, chipW: 50, seed: 0.5 },
      { a: 0, b: 2, chipW: 50, seed: 0.5 },
      { a: 1, b: 2, chipW: 90, seed: 0.5 },
    ];
    const { pos } = layoutForest({ items, parent, blocks: [{ root: 0, at: [0, 0], sides: 'right' }], links });
    expect(metrics(items, links, pos)).toMatchObject({ chipsOnCells: 0, hiddenLabels: 0, cellOverlaps: 0 });
  });

  it('keeps two blocks apart by moving subtrees off their facing sides', () => {
    const one = tree(25, 6),
      two = tree(25, 7);
    const shift = (id: number) => id + 1000;
    const items = [...one.items, ...two.items.map((it) => ({ ...it, id: shift(it.id) }))];
    const parent = new Map([...one.parent, ...[...two.parent].map(([c, p]) => [shift(c), shift(p)] as [number, number])]);
    const links = [...one.links, ...two.links.map((l) => ({ ...l, a: shift(l.a), b: shift(l.b) }))];
    const { pos } = layoutForest({
      items,
      parent,
      links,
      apart: 400,
      blocks: [
        { root: 0, at: [-1200, 0], sides: 'both' },
        { root: 1000, at: [1200, 0], sides: 'both' },
      ],
    });
    const right = Math.max(...one.items.map((it) => pos.get(it.id)![0] + it.halfW));
    const left = Math.min(...two.items.map((it) => pos.get(shift(it.id))![0] - it.halfW));
    expect(left - right).toBeGreaterThanOrEqual(400);
  });
});
