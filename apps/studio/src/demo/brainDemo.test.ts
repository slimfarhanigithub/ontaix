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
  SPACING_LARGE,
  SPACING_SMALL,
  startBrain,
  stopBrain,
  STORY_DOMAINS,
} from './brainDemo';
import type { BrainProposal, BrainQuestion, BrainRig, BrainRoute } from './brainRig';
import { brainPoints, growthOrder, lobesOf, neighboursOf } from './brainShape';
import { namesFor, SOURCES } from './brainVocabulary';
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
    expect(d.stories).toBeGreaterThan(0);
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
    expect(e.joined.size).toBe(t.nodes.filter((n) => n.company === added && n.kind === 'concept').length);
    expect(e.aside.has(home.root as Node)).toBe(true);
  });

  it('grows the brain on from the concepts already there, once they have reached their places', () => {
    const s = createScene();
    northwindModel(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    expect(brainPhase(d, 1)).toBe('company');
    expect(brainPhase(d, d.act3 + 0.1)).toBe('brain');
    expect(bornCount(d, d.act3 + 1.2)).toBe(d.stories);
    expect(d.growAt).toBeCloseTo(d.act3 + 1.3);
    expect(bornDomains(d, d.growAt)).toBe(9);
    expect(brainGrown(d, d.duration)).toBe(true);
    expect(d.cells.length).toBeGreaterThan(1000);
    // The first brain cells bud from the joined concepts and the root.
    const starts = new Set([...d.joined.values()].map((p) => `${p.x},${p.y}`));
    starts.add(`${d.rootAt?.x},${d.rootAt?.y}`);
    const first = d.cells.slice(d.stories, d.stories + 40).filter((c) => starts.has(`${c.px},${c.py}`));
    expect(first.length).toBeGreaterThan(0);
  });

  it('lights the sources up under the model, maps them to its concepts, then grows new concepts, each mapped to a source', () => {
    const s = createScene();
    northwindModel(s);
    settleTweens(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    const story = d.cells.slice(0, d.stories);
    const buds = story.filter((c) => !c.story?.source);
    const sources = story.filter((c) => c.story?.source);
    expect(buds.length).toBe(12);
    expect(sources.map((c) => c.label)).toEqual(SOURCES.slice(0, 4));
    // Every new concept buds from one of the company's own concepts, in that concept's domain, with a name the model does not hold.
    const realNames = new Set([...d.joined.keys()].map((n) => n.label));
    for (const c of buds) {
      const from = c.story?.from as Node;
      expect(d.joined.has(from)).toBe(true);
      expect(c.domain).toBe(from.domain?.key ?? 'core');
      expect(realNames.has(c.label)).toBe(false);
    }
    // The sources light up first, from the end of the first act, under the model and the new concepts.
    expect(Math.min(...sources.map((c) => c.born))).toBe(ACT_ONE);
    expect(Math.max(...sources.map((c) => c.born))).toBeLessThan(Math.min(...buds.map((c) => c.born)));
    const lowest = Math.max(...[...d.joined.keys()].map((n) => n.y), ...buds.map((c) => c.story?.y ?? 0));
    for (const c of sources) expect(c.story?.y).toBeGreaterThan(lowest);
    expect(brainPhase(d, ACT_ONE + 0.1)).toBe('domains');
    // Each source maps to the company's concepts before any new concept buds; none is mapped twice.
    const firstBud = Math.min(...buds.map((c) => c.born));
    const toModel = d.binds.filter((b) => typeof b.to !== 'number');
    expect(toModel.length).toBeGreaterThan(sources.length);
    for (const b of toModel) expect(b.at).toBeLessThan(firstBud);
    expect(new Set(d.binds.map((b) => b.to)).size).toBe(d.binds.length);
    for (let k = 1; k < d.binds.length; k++) expect(d.binds[k].at).toBeGreaterThanOrEqual(d.binds[k - 1].at);
    // Every new concept is mapped to a source as it buds.
    for (const c of buds) {
      const i = d.cells.indexOf(c);
      const bind = d.binds.find((b) => b.to === i);
      expect(bind?.at).toBe(c.born);
      expect(d.cells[bind?.source as number].story?.source).toBe(true);
    }
    for (const b of d.binds) expect(b.at).toBeLessThan(d.act3);
    // Sources have no place in the brain: its bounds hold the brain only.
    const inBrain = [...d.cells.filter((c) => !c.story?.source), ...d.joined.values(), d.rootAt as { x: number; y: number }];
    expect(d.box).toEqual([
      Math.min(...inBrain.map((c) => c.x)),
      Math.min(...inBrain.map((c) => c.y)),
      Math.max(...inBrain.map((c) => c.x)),
      Math.max(...inBrain.map((c) => c.y)),
    ]);
  });

  it('stands the sources over the brain, each connected to the brain cells nearest it once they bud, more joining as it grows', () => {
    const s = createScene();
    northwindModel(s);
    settleTweens(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    // The cells stay in the order they are born.
    for (let k = 1; k < d.cells.length; k++) expect(d.cells[k].born).toBeGreaterThanOrEqual(d.cells[k - 1].born);
    const rig = d.rig as BrainRig;
    const sources = d.cells.flatMap((c, i) => (c.story?.source ? [i] : []));
    expect(sources.map((i) => d.cells[i].label)).toEqual(SOURCES);
    expect(rig.sources.map((x) => x.source)).toEqual(sources);
    // Four come from the second act; four more join while the brain grows.
    expect(rig.sources.filter((x) => !x.joins).length).toBe(4);
    for (const x of rig.sources.filter((x) => x.joins)) {
      expect(d.cells[x.source].born).toBeGreaterThan(d.growAt);
      expect(d.cells[x.source].born).toBeLessThan(d.growAt + GROW);
    }
    // Every source stands over the brain, across its width, inside the camera's frame, apart from the others.
    const [x0, y0, x1] = d.box;
    const brain = d.cells.filter((c) => !c.story?.source);
    for (const x of rig.sources) {
      const c = d.cells[x.source];
      expect(c.y).toBeLessThan(y0);
      expect(c.x).toBeGreaterThan(x0);
      expect(c.x).toBeLessThan(x1);
      expect(c.y).toBeGreaterThan(d.frame[1]);
      // It connects to the brain cells nearest it, each once that cell has budded, never before the source is in place.
      expect(x.links.length).toBe(6);
      const nearest = brain.map((b) => Math.hypot(b.x - c.x, b.y - c.y)).sort((a, b) => a - b)[5];
      for (const l of x.links) {
        const t = d.cells[l.cell];
        expect(t.story?.source).toBeFalsy();
        expect(Math.hypot(t.x - c.x, t.y - c.y)).toBeLessThanOrEqual(nearest + 1e-6);
        expect(l.at).toBeGreaterThan(t.born);
        expect(l.at).toBeGreaterThan(x.joins ? c.born : d.act3 + MIGRATE);
      }
    }
    const xs = rig.sources.map((x) => d.cells[x.source].x).sort((a, b) => a - b);
    for (let k = 1; k < xs.length; k++) expect(xs[k] - xs[k - 1]).toBeGreaterThan(3 * d.spacing);
  });

  it('fires one lobe after another once grown, along the brain relations, then the whole brain at once', () => {
    const s = createScene();
    companyAlone(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    const rig = d.rig as BrainRig;
    expect(rig.runs.map((r) => r.domain)).toEqual([...DOMAINS.map((x) => x.key), 'core']);
    expect(rig.runs[0].at).toBeGreaterThan(d.growAt + GROW);
    for (let k = 1; k < rig.runs.length; k++) expect(rig.runs[k].at).toBeGreaterThan(rig.runs[k - 1].at);
    // Each lobe fires from its landing cell, every cell after the one it fires from, all in the lobe.
    for (const r of rig.runs) {
      expect(d.cells[r.landing].domain).toBe(r.domain);
      expect(rig.fireAt[r.landing]).toBeGreaterThan(r.at);
    }
    const brain = d.cells.flatMap((c, i) => (c.story?.source ? [] : [i]));
    let along = 0;
    for (const i of brain) {
      expect(Number.isFinite(rig.fireAt[i])).toBe(true);
      expect(Number.isFinite(rig.cascadeAt[i])).toBe(true);
      expect(rig.cascadeAt[i]).toBeGreaterThan(rig.allAt);
      const f = rig.fireFrom[i];
      if (f >= 0) {
        along++;
        expect(d.cells[f].domain).toBe(d.cells[i].domain);
        expect(rig.fireAt[f]).toBeLessThan(rig.fireAt[i]);
      }
      const g = rig.cascadeFrom[i];
      if (g >= 0) expect(rig.cascadeAt[g]).toBeLessThan(rig.cascadeAt[i]);
    }
    // Most cells fire from a neighbour; the rest of a lobe, cut off by a groove, as the firing reaches it.
    expect(along).toBeGreaterThan(brain.length * 0.85);
    const lastLobe = Math.max(...brain.map((i) => rig.fireAt[i]));
    expect(rig.allAt).toBeGreaterThan(lastLobe);
    expect(rig.settledAt).toBe(Math.max(...brain.map((i) => rig.cascadeAt[i])));
    expect(rig.agentAt).toBeGreaterThan(rig.settledAt);
  });

  it('ends with agents: one asks across domains and proposes a concept a person approves, then every agent works on the brain', () => {
    const s = createScene();
    companyAlone(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    const rig = d.rig as BrainRig;
    expect(rig.agents.map((a) => a.name)).toEqual(['Procurement agent', 'Planning agent', 'Quality agent', 'Sales agent', 'Service agent', 'Finance agent']);
    const q = rig.question as BrainQuestion;
    const route = rig.routes[q.route];
    expect(route.stops.map((o) => o.label)).toEqual(['Supplier', 'Purchase order', 'Goods receipt', 'Delivery', 'Customer']);
    expect(route.period).toBe(0);
    expect(q.ask).toBe('Which suppliers delay our deliveries to customers?');
    expect(q.askAt).toBeGreaterThanOrEqual(rig.agentAt);
    expect(q.answerAt).toBeGreaterThan(q.returnAt);
    const p = rig.proposal as BrainProposal;
    expect(p.label).toBe('Supplier risk score');
    expect(p.from).toBe(route.stops[0]);
    expect(p.at).toBeGreaterThan(q.answerAt);
    expect(p.approveAt).toBeGreaterThan(p.at);
    expect(rig.backAt).toBeGreaterThan(p.approveAt);
    const brain = d.cells.filter((c) => !c.story?.source);
    // The proposal stands outside the brain: no brain cell lies beyond it on its way out.
    const [ox, oy] = [p.from.x, p.from.y];
    const out = Math.hypot(p.x - ox, p.y - oy);
    for (const c of brain) {
      expect(Math.hypot(c.x - p.x, c.y - p.y)).toBeGreaterThan(2 * d.spacing);
      const along = ((c.x - ox) * (p.x - ox) + (c.y - oy) * (p.y - oy)) / out;
      const side = Math.abs((c.x - ox) * (p.y - oy) - (c.y - oy) * (p.x - ox)) / out;
      if (side < d.spacing) expect(along).toBeLessThan(out);
    }
    // Every agent stands outside the brain, inside the camera's frame; the others appear once the camera pulls back.
    for (const a of rig.agents) {
      expect(Math.min(...brain.map((c) => Math.hypot(c.x - a.x, c.y - a.y)))).toBeGreaterThan(2 * d.spacing);
      expect(a.x).toBeGreaterThan(d.frame[0]);
      expect(a.x).toBeLessThan(d.frame[2]);
      expect(a.y).toBeGreaterThan(d.frame[1]);
      expect(a.y).toBeLessThan(d.frame[3]);
    }
    for (const a of rig.agents.slice(1)) expect(a.at).toBeGreaterThan(rig.backAt);
    // The sales agent hands over to the service agent on the customer.
    const hand = rig.routes.find((r) => r.handoff >= 0) as BrainRoute;
    expect(rig.agents[hand.from].name).toBe('Sales agent');
    expect(rig.agents[hand.to].name).toBe('Service agent');
    expect(hand.stops[hand.handoff].label).toBe('Customer');
    expect(rig.routes.filter((r) => r.period > 0).length).toBe(5);
    expect(d.duration).toBe(rig.end);
  });

  it('lights the sources up first and maps the story to them when the company starts with no concept', () => {
    const s = createScene();
    companyAlone(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL });
    const story = d.cells.slice(0, d.stories);
    const sources = story.filter((c) => c.story?.source);
    const grown = story.filter((c) => !c.story?.source);
    expect(sources.map((c) => c.label)).toEqual(SOURCES.slice(0, 4));
    expect(Math.max(...sources.map((c) => c.born))).toBeLessThan(Math.min(...grown.map((c) => c.born)));
    // A concept, never a domain, is mapped to its source as it buds.
    for (const c of grown) {
      const i = d.cells.indexOf(c);
      const bind = d.binds.find((b) => b.to === i);
      if (c.story?.hub) expect(bind).toBeUndefined();
      else expect(bind?.at).toBe(c.born);
    }
    expect(d.binds.length).toBe(grown.filter((c) => !c.story?.hub).length);
    expect(d.frame[3]).toBeGreaterThan(d.box[3]);
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
    const story = d.cells.slice(0, d.stories).filter((c) => !c.story?.source);
    const hubs = story.filter((c) => c.story?.hub);
    expect(hubs.map((c) => c.label)).toEqual(DOMAINS.slice(0, 3).map((x) => x.name));
    expect(story.length).toBe(3 * 7);
    expect(story[0].born).toBeGreaterThan(ACT_ONE);
    expect(bornCount(d, ACT_ONE - 0.01)).toBe(0);
    for (const c of story) expect(c.born).toBeLessThan(d.act3);
    // Every concept buds from its domain, every domain from the root.
    for (const c of story) {
      const hub = d.cells.findIndex((h) => h.story?.hub && h.domain === c.domain);
      expect(c.story?.parent).toBe(c.story?.hub ? -1 : hub);
    }
    const storyLinks = d.links.filter(([, b]) => b < d.stories);
    const across = storyLinks.filter(([a, b]) => d.cells[a].domain !== d.cells[b].domain);
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
    const firstHub = (d.cells.find((c) => c.story?.hub) as { born: number }).born;
    expect(bornDomains(d, firstHub - 0.01)).toBe(0);
    expect(bornDomains(d, firstHub)).toBe(1);
    expect(brainPhase(d, d.act3 + 0.1)).toBe('brain');
    expect(bornCount(d, d.act3)).toBe(d.stories);
    const grow0 = d.act3 + 0.6;
    const grown = (e: number) => bornCount(d, grow0 + e) - d.stories;
    expect(grown(GROW / 2) - grown(GROW / 4)).toBeGreaterThan(grown(GROW / 4));
    expect(d.growAt + GROW - d.act3).toBeLessThan(13);
    expect(d.duration).toBeLessThan(54);
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
    expect(d.stories).toBe(3 * 5 + 3);
    // Six sources over the brain, and four agents in a row under it.
    const rig = d.rig as BrainRig;
    expect(rig.sources.length).toBe(6);
    expect(rig.agents.map((a) => a.name)).toEqual(['Procurement agent', 'Quality agent', 'Sales agent', 'Service agent']);
    for (const a of rig.agents) expect(a.y).toBeGreaterThan(d.box[3]);
  });

  it('fills the brain with templates the tenant does not hold, after its shown domains', () => {
    const shown = [{ key: 'carbon', name: 'Carbon', color: '#123456' }];
    const picked = brainDomains(shown, new Set(['carbon', 'production']));
    expect(picked[0]).toBe(shown[0]);
    expect(picked.map((d) => d.key)).not.toContain('production');
    expect(picked.length).toBe(9);
    expect(picked[1].key).toBe('supply');
  });

  it('grows at once when animations are skipped', () => {
    const s = createScene();
    companyAlone(s);
    const d = startBrain(s, DOMAINS, 0, { spacing: SPACING_SMALL, instant: true });
    expect(brainGrown(d, 0)).toBe(true);
    expect(d.veil).toBe(1);
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
    // While the first agent works the camera closes in on it, then pulls back to every agent.
    const rig = d.rig as BrainRig;
    brainStep(s, v, rig.focusAt - 0.01);
    const wide = s.cam.ts;
    brainStep(s, v, rig.agentAt + 2);
    expect(s.cam.ts).toBeGreaterThan(wide);
    expect(s.cam.ts).toBeLessThanOrEqual(0.45);
    brainStep(s, v, rig.backAt + 2);
    expect(s.cam.ts).toBeCloseTo(wide);
    s.userZoomed = true;
    s.cam.ts = 1;
    brainStep(s, v, d.duration);
    expect(s.cam.ts).toBe(1);
  });
});
