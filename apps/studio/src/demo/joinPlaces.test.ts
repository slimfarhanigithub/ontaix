import { describe, expect, it } from 'vitest';

import { joinPlaces, SPACING_LARGE } from './brainDemo';
import { brainPoints, LOBE_CENTRES, lobesOf, seeded, STEM_TOP } from './brainShape';

const GAP = SPACING_LARGE * 1.9;

/** The placement as a search over every point for every concept, with the gap test over every point taken. */
function placeEveryPoint(pts: { x: number; y: number }[], lobes: number[], taken: Set<number>, asks: [number, number, number][]): number[] {
  const joinedPoints: number[] = [];
  const nearestFree = (ux: number, uy: number, ok: (i: number) => boolean): number => {
    let best = -1,
      bd = Infinity;
    pts.forEach((p, i) => {
      if (taken.has(i) || !ok(i)) return;
      const d = Math.hypot(p.x - ux, p.y - uy);
      if (d < bd) {
        bd = d;
        best = i;
      }
    });
    if (best >= 0) taken.add(best);
    return best;
  };
  const apart = (j: number) => joinedPoints.every((k) => Math.hypot(pts[j].x - pts[k].x, pts[j].y - pts[k].y) >= GAP);
  return asks.map(([lobe, ux, uy]) => {
    const inLobe = (j: number) => lobes[j] === lobe;
    let i = nearestFree(ux, uy, (j) => inLobe(j) && apart(j));
    if (i < 0) i = nearestFree(ux, uy, inLobe);
    if (i >= 0) joinedPoints.push(i);
    return i;
  });
}

describe('joinPlaces', () => {
  it('gives every concept the point a search over every point gives, lobes full or not', () => {
    const pts = brainPoints(SPACING_LARGE, 7);
    const lobes = lobesOf(pts, 9);
    const rnd = seeded(11);
    // Many concepts in a few lobes, so some lobes run out of points far enough apart, plus stem concepts.
    const asks: [number, number, number][] = [];
    for (let i = 0; i < 900; i++) {
      const lobe = i % 7 === 0 ? -1 : Math.floor(rnd() * 4);
      const [ux, uy] = lobe >= 0 ? LOBE_CENTRES[lobe] : STEM_TOP;
      asks.push([lobe, ux, uy]);
    }
    const takenA = new Set<number>([5]),
      takenB = new Set<number>([5]);
    const expected = placeEveryPoint(pts, lobes, takenA, asks);
    const places = joinPlaces(pts, lobes, takenB, GAP);
    const got = asks.map(([lobe, ux, uy]) => places.take(lobe, ux, uy));
    expect(got).toEqual(expected);
    expect([...takenB].sort()).toEqual([...takenA].sort());
    expect(got.filter((i) => i >= 0).length).toBeGreaterThan(800);
  });
});
