import { describe, expect, it } from 'vitest';

import { createScene } from '../canvas/state';
import { fixtureModel, northwindModel, settleTweens } from '../canvas/testModels';
import { ease } from '../canvas/colour';
import { DOMAIN_TEMPLATES } from '../canvas/constants';
import { dimOf, hitAt } from '../canvas/focus';
import type { Company, Node } from '../canvas/types';
import {
  ACT_ONE,
  bornCount,
  bornDomains,
  bornLinks,
  brainAlpha,
  brainDomains,
  brainGrown,
  brainPhase,
  brainStep,
  FADE_OUT,
  GROW,
  MIGRATE,
  pauseBrain,
  replayBrain,
  resumeBrain,
  SPACING_LARGE,
  SPACING_SMALL,
  startBrain,
  stopBrain,
  STORY_DOMAINS,
} from './brainDemo';
import { brainPoints, growthOrder, lobesOf, neighboursOf } from './brainShape';
import { namesFor } from './brainVocabulary';
import type { View } from '../canvas/view';

const DOMAINS = DOMAIN_TEMPLATES.map((d) => ({ key: d.key, name: d.name, color: d.color }));

const view = (W: number, H: number): View => ({ W, H, panelOff: () => false }) as unknown as View;

/** Northwind Industries with its root only: a company with no concept yet. */
function companyAlone(s: ReturnType<typeof createScene>): Company {
  const company = northwindModel(s);
  s.nodes = s.nodes.filter((n) => n === company.root);
  s.links = [];
  return company;
}

/** Runs the canvas's tweens to `t`, as the physics step does. */
function tweenTo(nodes: Iterable<Node>, t: number): void {
  for (const n of nodes) {
    if (!n.tween) continue;
    const q = Math.min(1, Math.max(0, (t - n.tween.start) / 1.3));
    const e = ease(q);
    n.x = n.tween.fx + (n.tween.tx - n.tween.fx) * e;
    n.y = n.tween.fy + (n.tween.ty - n.tween.fy) * e;
    if (q >= 1) {
      n.tween = null;
      n.pinned = true;
    }
  }
}

describe('the brain shape', () => {
  it('draws the same points from the same seed, about 3,400 on a large screen and 1,800 on a phone', () => {
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
  it('starts from the company alone: the root moves to the stem at once, and comes back on stop', () => {
    const s = createScene();
    const company = companyAlone(s);
    settleTweens(s);
    const root = company.root as Node;
    const before = [root.x, root.y];
    const home = [company.x, company.y];
    const d = startBrain(s, DOMAINS, 100, { spacing: SPACING_SMALL });
    expect(s.brain).toBe(d);
    expect(d.root).toBe(root);
    expect(d.company).toBe(company.name);
    expect(d.lobes).toBe(9);
    expect(d.joined.size).toBe(0);
    expect(root.tween?.start).toBe(100);
    expect([root.tween?.tx, root.tween?.ty]).toEqual([company.x, company.y]);
    stopBrain(s, 110);
    expect([company.x, company.y]).toEqual(home);
    expect([root.tween?.tx, root.tween?.ty]).toEqual(before);
  });

  it('builds on the model already there: every concept joins the lobe of its domain, other companies are set aside', () => {
    const s = createScene();
    const { northwind, aurora } = fixtureModel(s);
    settleTweens(s);
    const before = new Map(s.nodes.map((n) => [n, [n.x, n.y]]));
    const concepts = s.nodes.filter((n) => n.company === northwind && n.kind === 'concept' && !n.dying);
    s.activeCompany = northwind;
    const d = startBrain(s, DOMAINS, 100, { spacing: SPACING_SMALL });
    expect(d.stories).toBe(0);
    expect(d.storyDomains).toBe(0);
    expect([...d.joined.keys()].sort((a, b) => a.id - b.id)).toEqual(concepts.sort((a, b) => a.id - b.id));
    for (const n of s.nodes.filter((x) => x.company === aurora)) expect(d.aside.has(n)).toBe(true);
    for (const n of d.joined.keys()) expect(d.aside.has(n)).toBe(false);
    // Joined concepts never touch one another and never share a place with a brain cell.
    const places = [...d.joined.values()];
    for (let i = 0; i < places.length; i++)
      for (let j = i + 1; j < places.length; j++)
        expect(Math.hypot(places[i].x - places[j].x, places[i].y - places[j].y)).toBeGreaterThan(d.spacing * 1.5);
    const placed = new Set(places.map((p) => `${p.x},${p.y}`));
    for (const c of d.cells) expect(placed.has(`${c.x},${c.y}`)).toBe(false);
    // Each joins its own domain's lobe: nearer its lobe's brain cells than any other lobe's, on the whole.
    let home = 0;
    for (const [n, p] of d.joined) {
      let best = d.cells[0];
      for (const c of d.cells) if (Math.hypot(c.x - p.x, c.y - p.y) < Math.hypot(best.x - p.x, best.y - p.y)) best = c;
      if (best.domain === n.domain?.key) home++;
    }
    expect(home).toBeGreaterThan(d.joined.size * 0.8);
    // The model stands where it was through the first act, then the root and its concepts leave together.
    const root = northwind.root as Node;
    for (const n of [...d.joined.keys(), root]) {
      expect([n.x, n.y]).toEqual(before.get(n));
      expect(n.tween?.start).toBe(100 + d.act3);
    }
    expect(dimOf(s, concepts[0])).toBe(1);
    expect(hitAt(s, concepts[0].x, concepts[0].y, null)).toBe(concepts[0]);
    tweenTo(s.nodes, 100 + d.act3 + 1.3);
    for (const [n, p] of d.joined) expect(Math.hypot(n.x - p.x, n.y - p.y)).toBeLessThan(1e-6);
    expect(Math.hypot(root.x - (d.rootAt?.x ?? 0), root.y - (d.rootAt?.y ?? 0))).toBeLessThan(1e-6);
    // Stop puts every real cell back.
    stopBrain(s, 130);
    for (const n of s.nodes) expect([n.tween?.tx, n.tween?.ty]).toEqual(before.get(n));
  });

  it('builds on the company being taught, or on the company that holds concepts when the one taught has none', () => {
    const s = createScene();
    const { aurora } = fixtureModel(s);
    s.activeCompany = aurora;
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    expect(d.company).toBe(aurora.name);
    expect([...d.joined.keys()].every((n) => n.company === aurora)).toBe(true);
    expect(d.joined.size).toBeGreaterThan(0);

    // A company added after a reset is taught while the home company is empty: the brain builds on the one with concepts.
    const t = createScene();
    const { northwind: home, aurora: added } = fixtureModel(t);
    t.nodes = t.nodes.filter((n) => n.company !== home || n === home.root);
    t.links = t.links.filter((l) => l.a.company !== home && l.b.company !== home);
    t.activeCompany = home;
    const e = startBrain(t, DOMAINS, 0, { spacing: SPACING_SMALL });
    expect(e.company).toBe(added.name);
    expect(e.stories).toBe(0);
    expect(e.joined.size).toBe(t.nodes.filter((n) => n.company === added && n.kind === 'concept').length);
    expect(e.aside.has(home.root as Node)).toBe(true);
  });

  it('grows the brain on from the concepts already there, once they have reached their places', () => {
    const s = createScene();
    northwindModel(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    expect(brainPhase(d, 1)).toBe('company');
    expect(brainPhase(d, d.act3 + 0.1)).toBe('brain');
    expect(bornCount(d, d.act3 + 1.2)).toBe(0);
    expect(d.growAt).toBeCloseTo(d.act3 + 1.3);
    expect(bornDomains(d, d.growAt)).toBe(9);
    expect(brainGrown(d, d.duration)).toBe(true);
    expect(d.cells.length).toBeGreaterThan(1000);
    // The first brain cells bud from the joined concepts and the root.
    const starts = new Set([...d.joined.values()].map((p) => `${p.x},${p.y}`));
    starts.add(`${d.rootAt?.x},${d.rootAt?.y}`);
    const first = d.cells.slice(0, 40).filter((c) => starts.has(`${c.px},${c.py}`));
    expect(first.length).toBeGreaterThan(0);
  });

  it('replays from the model as it stood, and a paused demo holds its concepts back', () => {
    const s = createScene();
    northwindModel(s);
    settleTweens(s);
    const before = new Map(s.nodes.map((n) => [n, [n.x, n.y]]));
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    const n = [...d.joined.keys()][0];
    pauseBrain(d, 1);
    resumeBrain(d, 11);
    expect(n.tween?.start).toBe(d.act3 + 10);
    tweenTo(s.nodes, 40);
    replayBrain(s, d, 50);
    expect([n.x, n.y]).toEqual(before.get(n));
    expect(n.tween?.start).toBe(50 + d.act3);
    expect(brainPhase(d, 50)).toBe('company');
  });

  it('builds on the model at once when animations are skipped', () => {
    const s = createScene();
    northwindModel(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL, instant: true });
    expect(brainGrown(d, 0)).toBe(true);
    for (const [n, p] of d.joined) {
      expect(n.tween).toBeNull();
      expect([n.x, n.y]).toEqual([p.x, p.y]);
    }
  });

  it('grows three domains beside the company, each with named concepts and relations within and across them', () => {
    const s = createScene();
    companyAlone(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    expect(d.storyDomains).toBe(STORY_DOMAINS);
    const story = d.cells.slice(0, d.stories);
    const hubs = story.filter((c) => c.story?.hub);
    expect(hubs.map((c) => c.label)).toEqual(DOMAINS.slice(0, 3).map((x) => x.name));
    expect(story.length).toBe(3 * 7);
    expect(story[0].born).toBe(ACT_ONE);
    expect(bornCount(d, ACT_ONE - 0.01)).toBe(0);
    for (const c of story) expect(c.born).toBeLessThan(d.act3);
    // Every concept buds from its domain, every domain from the root.
    for (const c of story) {
      const hub = story.findIndex((h) => h.story?.hub && h.domain === c.domain);
      expect(c.story?.parent).toBe(c.story?.hub ? -1 : hub);
    }
    const storyLinks = d.links.filter(([, b]) => b < d.stories);
    const across = storyLinks.filter(([a, b]) => story[a].domain !== story[b].domain);
    expect(across.length).toBe(3);
    expect(storyLinks.length).toBeGreaterThan(across.length);
    expect(new Set(story.map((c) => c.label)).size).toBe(story.length);
    // No brain cell repeats a story name.
    const brainNames = new Set(d.cells.slice(d.stories).map((c) => c.label));
    for (const c of story) expect(brainNames.has(c.label)).toBe(false);
  });

  it('plays the acts in order and grows the rest of the brain fast, faster and faster', () => {
    const s = createScene();
    companyAlone(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    expect(brainPhase(d, 1)).toBe('company');
    expect(brainPhase(d, ACT_ONE + 0.1)).toBe('domains');
    expect(bornDomains(d, ACT_ONE + 0.1)).toBe(1);
    expect(brainPhase(d, d.act3 + 0.1)).toBe('brain');
    expect(bornCount(d, d.act3)).toBe(d.stories);
    const grow0 = d.act3 + 0.6;
    const grown = (e: number) => bornCount(d, grow0 + e) - d.stories;
    expect(grown(GROW / 2) - grown(GROW / 4)).toBeGreaterThan(grown(GROW / 4));
    expect(d.duration - d.act3).toBeLessThan(12);
    expect(d.duration).toBeLessThan(30);
    expect(brainGrown(d, d.duration - 0.5)).toBe(false);
    expect(brainGrown(d, d.duration)).toBe(true);
    expect(brainPhase(d, d.duration)).toBe('grown');
    expect(bornDomains(d, d.duration)).toBe(9);
    expect(bornLinks(d, d.duration)).toBeGreaterThan(d.cells.length);
  });

  it('grows nothing on the root or a story cell, every brain cell from a cell or the root close by', () => {
    const s = createScene();
    companyAlone(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    const placed = new Set(d.cells.slice(0, d.stories).map((c) => `${c.x},${c.y}`));
    placed.add(`${d.root?.tween?.tx},${d.root?.tween?.ty}`);
    const brain = d.cells.slice(d.stories);
    for (const c of brain) {
      expect(placed.has(`${c.x},${c.y}`)).toBe(false);
      if (c.linked) expect(Math.hypot(c.x - c.px, c.y - c.py)).toBeLessThan(d.spacing * 40);
    }
    expect(brain.filter((c) => c.linked).length).toBeGreaterThan(brain.length * 0.95);
  });

  it('grows a shorter story on a phone', () => {
    const s = createScene();
    companyAlone(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL, small: true });
    expect(d.stories).toBe(3 * 5);
  });

  it('fills the brain with templates the tenant does not hold, after its shown domains', () => {
    const shown = [{ key: 'carbon', name: 'Carbon', color: '#123456' }];
    const picked = brainDomains(shown, new Set(['carbon', 'production']));
    expect(picked[0]).toBe(shown[0]);
    expect(picked.map((d) => d.key)).not.toContain('production');
    expect(picked.length).toBe(9);
    expect(picked[1].key).toBe('supply');
  });

  it('pauses, resumes and replays from the company alone', () => {
    const s = createScene();
    companyAlone(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    pauseBrain(d, 20);
    const held = bornCount(d, 20);
    expect(bornCount(d, 35)).toBe(held);
    resumeBrain(d, 35);
    expect(bornCount(d, 35)).toBe(held);
    expect(bornCount(d, 40)).toBeGreaterThan(held);
    replayBrain(s, d, 50);
    expect(bornCount(d, 50)).toBe(0);
    expect(brainPhase(d, 50)).toBe('company');
  });

  it('grows at once when animations are skipped', () => {
    const s = createScene();
    companyAlone(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL, instant: true });
    expect(brainGrown(d, 0)).toBe(true);
    expect(d.veil).toBe(1);
    replayBrain(s, d, 10);
    expect(brainGrown(d, 10)).toBe(true);
  });

  it('fades out after stop, brings the cells set aside back, and then leaves the scene', () => {
    const s = createScene();
    fixtureModel(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    const other = [...d.aside][0];
    stopBrain(s, 10);
    expect(brainAlpha(d, 10)).toBe(1);
    expect(brainAlpha(d, 10 + FADE_OUT / 2)).toBeCloseTo(0.5);
    brainStep(s, view(1440, 900), 10 + FADE_OUT / 2);
    expect(dimOf(s, other)).toBeCloseTo(0.5);
    brainStep(s, view(1440, 900), 10 + FADE_OUT + 0.01);
    expect(s.brain).toBeNull();
    expect(dimOf(s, other)).toBe(1);
  });

  it('keeps the camera close on the story, then pulls back past the usual 0.3 zoom, until the user zooms', () => {
    const s = createScene();
    companyAlone(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_LARGE });
    const v = view(1440, 900);
    brainStep(s, v, 1);
    expect(s.cam.ts).toBe(1);
    brainStep(s, v, d.act3 - 0.1);
    const story = s.cam.ts;
    expect(story).toBeGreaterThanOrEqual(0.3);
    brainStep(s, v, d.act3 + MIGRATE / 2);
    expect(s.cam.ts).toBeLessThan(story);
    brainStep(s, v, d.duration);
    expect(s.cam.ts).toBeLessThan(0.3);
    s.userZoomed = true;
    s.cam.ts = 1;
    brainStep(s, v, d.duration);
    expect(s.cam.ts).toBe(1);
  });
});
