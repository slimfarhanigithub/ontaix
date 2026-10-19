import { describe, expect, it } from 'vitest';

import { createScene } from '../canvas/state';
import { northwindModel, settleTweens } from '../canvas/testModels';
import { DOMAIN_TEMPLATES } from '../canvas/constants';
import {
  bornCount,
  bornLinks,
  brainAlpha,
  brainGrown,
  brainStep,
  DURATION,
  FADE_OUT,
  pauseBrain,
  replayBrain,
  resumeBrain,
  SPACING_LARGE,
  SPACING_SMALL,
  startBrain,
  stopBrain,
} from './brainDemo';
import { brainPoints, growthOrder, lobesOf, neighboursOf } from './brainShape';
import { namesFor } from './brainVocabulary';
import type { View } from '../canvas/view';

const DOMAINS = DOMAIN_TEMPLATES.map((d) => ({ key: d.key, name: d.name, color: d.color }));

const view = (W: number, H: number): View => ({ W, H, panelOff: () => false }) as unknown as View;

describe('the brain shape', () => {
  it('draws the same points from the same seed, about 3,000 on a large screen and 1,600 on a phone', () => {
    const a = brainPoints(SPACING_LARGE, 7);
    expect(brainPoints(SPACING_LARGE, 7)).toEqual(a);
    expect(a.length).toBeGreaterThan(2600);
    expect(a.length).toBeLessThan(3600);
    const small = brainPoints(SPACING_SMALL, 7).length;
    expect(small).toBeGreaterThan(1300);
    expect(small).toBeLessThan(2000);
  });

  it('holds a cerebrum, a cerebellum and a brain stem, the stem under the cerebrum', () => {
    const pts = brainPoints(SPACING_SMALL);
    const parts = new Set(pts.map((p) => p.part));
    expect([...parts].sort()).toEqual(['cerebellum', 'cerebrum', 'stem']);
    const lowest = (part: string) => Math.max(...pts.filter((p) => p.part === part).map((p) => p.y));
    expect(lowest('stem')).toBeGreaterThan(lowest('cerebrum'));
    for (const p of pts) {
      expect(Math.abs(p.x)).toBeLessThan(1.1);
      expect(p.y).toBeGreaterThan(-0.75);
      expect(p.y).toBeLessThan(0.95);
    }
  });

  it('gives every domain one lobe and the stem to no domain', () => {
    const pts = brainPoints(SPACING_SMALL);
    for (const count of [1, 3, 9, 12]) {
      const lobes = lobesOf(pts, count);
      const used = new Set(lobes.filter((l) => l >= 0));
      expect(used.size).toBe(count);
      pts.forEach((p, i) => expect(lobes[i] === -1).toBe(p.part === 'stem'));
    }
  });

  it('grows every point once, each after its parent, seeds first', () => {
    const pts = brainPoints(SPACING_SMALL);
    const near = neighboursOf(pts, SPACING_SMALL * 1.6);
    const seeds = [0, Math.floor(pts.length / 2)];
    const { order, parent } = growthOrder(pts, near, seeds);
    expect(order.length).toBe(pts.length);
    expect(new Set(order).size).toBe(pts.length);
    expect(order.slice(0, 2).sort((a, b) => a - b)).toEqual(seeds);
    const rank = new Map(order.map((p, i) => [p, i]));
    for (const p of order) if (parent[p] >= 0) expect(rank.get(parent[p])).toBeLessThan(rank.get(p) as number);
  });
});

describe('the brain vocabulary', () => {
  it('starts with the plain nouns of the domain and never repeats a name', () => {
    const names = namesFor('sales', 'Sales', 3);
    const first = Array.from({ length: 300 }, () => names.next());
    expect(first[0]).toBe('Customer');
    expect(new Set(first).size).toBe(first.length);
    // Sales has 8 qualifiers for 16 nouns: the 129th name is the first to come back, for a plant.
    expect(first[127]).not.toContain(' · ');
    expect(first[128]).toBe('Customer · Lyon');
  });

  it('builds names for a custom domain from its name', () => {
    expect(namesFor('carbon', 'Carbon', 1).next()).toBe('Carbon record');
  });
});

describe('the demo brain', () => {
  it('moves the real cells into the brain, roots to the stem, and puts them back on stop', () => {
    const s = createScene();
    northwindModel(s);
    settleTweens(s);
    const before = new Map(s.nodes.map((n) => [n, [n.x, n.y]]));
    const company = s.companies[0];
    const home = [company.x, company.y];
    const d = startBrain(s, DOMAINS, 100, { spacing: SPACING_SMALL });
    expect(s.brain).toBe(d);
    expect(d.realConcepts).toBe(s.nodes.filter((n) => n.kind === 'concept').length);
    expect(d.lobes).toBe(9);
    const targets = s.nodes.map((n) => n.tween && [n.tween.tx, n.tween.ty]);
    expect(targets.every(Boolean)).toBe(true);
    expect(new Set(targets.map((p) => String(p))).size).toBe(s.nodes.length);
    expect(s.nodes.find((n) => n.kind === 'root')?.tween?.tx).toBe(company.x);
    stopBrain(s, 110);
    expect([company.x, company.y]).toEqual(home);
    for (const n of s.nodes) expect([n.tween?.tx, n.tween?.ty]).toEqual(before.get(n));
  });

  it('grows nothing that sits on a real cell, every cell from a cell or a real cell close by', () => {
    const s = createScene();
    northwindModel(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    const real = new Set(s.nodes.map((n) => `${n.tween?.tx},${n.tween?.ty}`));
    for (const c of d.cells) {
      expect(real.has(`${c.x},${c.y}`)).toBe(false);
      if (c.linked) expect(Math.hypot(c.x - c.px, c.y - c.py)).toBeLessThan(d.spacing * 40);
    }
    expect(d.cells.filter((c) => c.linked).length).toBeGreaterThan(d.cells.length * 0.95);
  });

  it('grows slowly at first, faster and faster, and is grown after DURATION seconds', () => {
    const s = createScene();
    northwindModel(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    const at = (t: number) => bornCount(d, t);
    expect(at(0)).toBe(0);
    expect(at(2)).toBeLessThan(at(DURATION / 2) / 10);
    expect(at(DURATION * 0.75) - at(DURATION / 2)).toBeGreaterThan(at(DURATION / 4));
    expect(brainGrown(d, DURATION - 1)).toBe(false);
    expect(brainGrown(d, DURATION)).toBe(true);
    expect(bornLinks(d, DURATION)).toBeGreaterThan(d.cells.length);
  });

  it('pauses, resumes and replays', () => {
    const s = createScene();
    northwindModel(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    pauseBrain(d, 20);
    const held = bornCount(d, 20);
    expect(bornCount(d, 35)).toBe(held);
    resumeBrain(d, 35);
    expect(bornCount(d, 35)).toBe(held);
    expect(bornCount(d, 40)).toBeGreaterThan(held);
    replayBrain(s, d, 50);
    expect(bornCount(d, 50)).toBe(0);
  });

  it('grows at once when animations are skipped', () => {
    const s = createScene();
    northwindModel(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL, instant: true });
    expect(brainGrown(d, 0)).toBe(true);
  });

  it('fades out after stop and then leaves the scene', () => {
    const s = createScene();
    northwindModel(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    stopBrain(s, 10);
    expect(brainAlpha(d, 10)).toBe(1);
    expect(brainAlpha(d, 10 + FADE_OUT / 2)).toBeCloseTo(0.5);
    brainStep(s, view(1440, 900), 10 + FADE_OUT + 0.01);
    expect(s.brain).toBeNull();
  });

  it('pulls the camera back as the brain grows, past the usual 0.3 zoom, until the user zooms', () => {
    const s = createScene();
    northwindModel(s);
    startBrain(s, DOMAINS, 0, { spacing: SPACING_LARGE });
    const v = view(1440, 900);
    brainStep(s, v, 5);
    const early = s.cam.ts;
    brainStep(s, v, DURATION);
    expect(s.cam.ts).toBeLessThan(early);
    expect(s.cam.ts).toBeLessThan(0.3);
    s.userZoomed = true;
    s.cam.ts = 1;
    brainStep(s, v, DURATION);
    expect(s.cam.ts).toBe(1);
  });
});
