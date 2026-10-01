import { mulberry32 } from '../runtime/mulberry32';
import { setSource } from '../runtime/rng';
import { curve, qp } from './links';
import { linkShape, measureLayout, type MetricCell } from './layoutMetrics';
import { addLink, addNode, createScene } from './state';

const cell = (x: number, y: number, group: string | null = null, halfW = 40): MetricCell => ({
  x,
  y,
  r: 24,
  box: { x0: x - halfW, y0: y - 28, x1: x + halfW, y1: y + 60 },
  group,
});

describe('layout metrics', () => {
  beforeEach(() => setSource(mulberry32(3)));
  afterEach(() => setSource(null));

  it('follows the curve the link renderer draws', () => {
    const s = createScene();
    const a = addNode(s, { x: 10, y: 20 }),
      b = addNode(s, { x: 410, y: 180 });
    const l = addLink(s, a, b, 'rel', 230, 'has', 0.83);
    const { cx, cy } = curve(l);
    const sh = linkShape(a, b, l.seed, 4);
    const chord = Math.hypot(b.x - a.x, b.y - a.y);
    const u0 = (a.r * 1.05) / chord,
      u1 = 1 - (b.r * 1.05 + 10) / chord;
    expect(sh.pts[0][0]).toBeCloseTo(qp(l, cx, cy, u0)[0], 9);
    expect(sh.pts[4][1]).toBeCloseTo(qp(l, cx, cy, u1)[1], 9);
    expect(sh.chip!.x).toBeCloseTo(qp(l, cx, cy, (u0 + u1) / 2)[0], 9);
  });

  it('counts crossing links but not links that share a cell', () => {
    const cells = [cell(0, 0), cell(400, 400), cell(0, 400), cell(400, 0)];
    const m = measureLayout(cells, [
      { a: 0, b: 1, seed: 0.5, chipW: 0 },
      { a: 2, b: 3, seed: 0.5, chipW: 0 },
      { a: 0, b: 2, seed: 0.5, chipW: 0 },
    ]);
    expect(m.crossings).toBe(1);
  });

  it('counts overlapping cells, hidden chips, chips on cells and links through cells', () => {
    const near = measureLayout([cell(0, 0), cell(30, 30)], []);
    expect(near.cellOverlaps).toBe(1);
    const short = measureLayout([cell(0, 0), cell(100, 0)], [{ a: 0, b: 1, seed: 0.5, chipW: 40 }]);
    expect(short.hiddenLabels).toBe(1);
    const wide = measureLayout([cell(0, 0, null, 90), cell(200, 0, null, 90)], [{ a: 0, b: 1, seed: 0.5, chipW: 140 }]);
    expect(wide.chipsOnCells).toBeGreaterThan(0);
    const clear = measureLayout([cell(0, 0), cell(300, 0)], [{ a: 0, b: 1, seed: 0.5, chipW: 60 }]);
    expect(clear).toMatchObject({ chipsOnCells: 0, hiddenLabels: 0, cellOverlaps: 0 });
    const through = measureLayout([cell(0, 0), cell(200, 0), cell(400, 0)], [{ a: 0, b: 2, seed: 0.5, chipW: 0 }]);
    expect(through.linksThroughCells).toBe(1);
  });

  it('counts domain regions that come closer than their two paddings', () => {
    const close = measureLayout([cell(0, 0, 'a'), cell(0, 100, 'a'), cell(150, 0, 'b')], []);
    expect(close.regionOverlaps).toBe(1);
    const far = measureLayout([cell(0, 0, 'a'), cell(0, 100, 'a'), cell(600, 0, 'b')], []);
    expect(far.regionOverlaps).toBe(0);
  });
});
