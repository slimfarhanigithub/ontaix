import { mulberry32 } from '../runtime/mulberry32';
import { random, setSource } from '../runtime/rng';
import { repel } from './physics';
import { addNode, createScene } from './state';
import type { Node } from './types';

/** The repulsion as a pass over every pair of nodes, in index order. */
function repelEveryPair(nodes: Node[], dt: number): void {
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j];
      if ((a.split && a.split.from === b) || (b.split && b.split.from === a)) continue;
      let dx = b.x - a.x,
        dy = b.y - a.y,
        d2 = dx * dx + dy * dy;
      if (d2 < 1) {
        dx = random() - 0.5;
        dy = random() - 0.5;
        d2 = 1;
      }
      const d = Math.sqrt(d2);
      const want = (a.rt + b.rt) * 3.6;
      if (d < want) {
        const f = ((want - d) / want) * 950,
          fx = (dx / d) * f,
          fy = (dy / d) * f;
        if (!a.fixed && !a.drag) {
          a.vx -= fx * dt;
          a.vy -= fy * dt;
        }
        if (!b.fixed && !b.drag) {
          b.vx += fx * dt;
          b.vy += fy * dt;
        }
      }
    }
  }
}

/** A crowded model: cells of two sizes, some fixed, dragged, dividing or on top of one another. */
function crowd(seed: number, count: number, spread: number): Node[] {
  setSource(mulberry32(seed));
  const s = createScene();
  for (let i = 0; i < count; i++) {
    const n = addNode(s, {
      x: (random() - 0.5) * spread,
      y: (random() - 0.5) * spread,
      vx: (random() - 0.5) * 40,
      vy: (random() - 0.5) * 40,
      rt: i % 7 === 0 ? 16 : 24,
      fixed: i % 50 === 0,
      drag: i % 61 === 0,
    });
    if (i % 23 === 0 && i > 0) {
      const from = s.nodes[i - 1];
      n.x = from.x;
      n.y = from.y;
      n.split = { from, start: 0, dur: 0.85, ang: 0, broken: false, kicked: false, D: 70 };
    } else if (i % 31 === 0 && i > 0) {
      // Right on top of another cell: the pair takes a random nudge.
      n.x = s.nodes[i - 1].x;
      n.y = s.nodes[i - 1].y;
    }
  }
  return s.nodes;
}

describe('repulsion', () => {
  afterEach(() => setSource(null));

  it('adds the same forces, in the same order, as a pass over every pair', () => {
    for (const [seed, count, spread] of [
      [1, 400, 2400],
      [2, 700, 1200],
      [3, 60, 300],
    ]) {
      const a = crowd(seed, count, spread);
      const b = crowd(seed, count, spread);
      setSource(mulberry32(99));
      repelEveryPair(a, 1 / 60);
      const nextA = random();
      setSource(mulberry32(99));
      repel(b, 1 / 60);
      const nextB = random();
      for (let i = 0; i < count; i++) {
        expect(b[i].vx).toBe(a[i].vx);
        expect(b[i].vy).toBe(a[i].vy);
      }
      // The coincident pairs drew the same random nudges, so the stream stands at the same place.
      expect(nextB).toBe(nextA);
    }
  });

  it('measures the distance to the cells near a cell only, not to every cell', () => {
    const nodes = crowd(5, 2000, 40000);
    const sqrt = vi.spyOn(Math, 'sqrt');
    repel(nodes, 1 / 60);
    const pairs = sqrt.mock.calls.length;
    sqrt.mockRestore();
    expect(pairs).toBeLessThan(2000 * 40);
    expect(pairs).toBeLessThan((2000 * 1999) / 2 / 20);
  });
});
