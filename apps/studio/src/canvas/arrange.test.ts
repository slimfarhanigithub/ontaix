import { mulberry32 } from '../runtime/mulberry32';
import { setSource } from '../runtime/rng';
import { arrangeAll, arrangeCell, arrangeDomain, arrangeLineage, stageOrigin } from './arrange';
import { DOMAIN_R } from './constants';
import { sceneMetrics } from './sceneMetrics';
import { addCompany, addLink, addNode, addSource, createScene, domainOf, find, type SceneState } from './state';
import { fixtureModel, northwindModel, settleTweens, syntheticModel } from './testModels';
import type { Node } from './types';
import type { View } from './view';

const view = { W: 1440, H: 900, panelOff: () => false } as unknown as View;

/** Arranges everything, lets the tweens land, then stages `stage` and returns the cells it moved. */
function staged(s: SceneState, stage: (s: SceneState) => void): Set<Node> {
  arrangeAll(s);
  settleTweens(s);
  stage(s);
  const moved = new Set(s.nodes.filter((n) => n.tween));
  settleTweens(s);
  return moved;
}

describe('arrange', () => {
  beforeEach(() => setSource(mulberry32(3)));
  afterEach(() => setSource(null));

  it('lays a birth tree of one domain product out with no crossing, overlap or hidden action', () => {
    const s = createScene();
    const c = syntheticModel(s, 120, 5, 0);
    const production = domainOf(s, 'production', c);
    for (const n of s.nodes) if (n.domain) n.domain = production;
    arrangeAll(s);
    settleTweens(s);
    expect(sceneMetrics(s)).toMatchObject({
      crossings: 0,
      cellOverlaps: 0,
      chipOverlaps: 0,
      chipsOnCells: 0,
      hiddenLabels: 0,
    });
  });

  it('lays Northwind out with one clear region per domain product, nothing covered, at most two crossings', () => {
    const s = createScene();
    const c = northwindModel(s);
    arrangeAll(s);
    expect(c.root!.tween).toBeNull();
    expect([c.root!.x, c.root!.y]).toEqual([c.x, c.y]);
    settleTweens(s);
    const m = sceneMetrics(s);
    expect(m).toMatchObject({
      cellOverlaps: 0,
      chipOverlaps: 0,
      chipsOnCells: 0,
      hiddenLabels: 0,
      regionOverlaps: 0,
      headerOverlaps: 0,
    });
    expect(m.crossings).toBeLessThanOrEqual(2);
    expect(m.linksThroughCells).toBeLessThanOrEqual(2);
    expect(s.userZoomed).toBe(false);
  });

  it('keeps the camera at a zoom that draws labels when the fit would be smaller', () => {
    const s = createScene();
    northwindModel(s);
    arrangeAll(s, undefined, view);
    expect(s.userZoomed).toBe(true);
    expect(s.cam.ts).toBeCloseTo(0.55, 9);
  });

  it('lays the fixture model out with no overlap and keeps the two companies apart', () => {
    const s = createScene();
    const { northwind, aurora } = fixtureModel(s);
    arrangeAll(s);
    settleTweens(s);
    const m = sceneMetrics(s);
    expect(m).toMatchObject({
      cellOverlaps: 0,
      chipOverlaps: 0,
      chipsOnCells: 0,
      hiddenLabels: 0,
      regionOverlaps: 0,
      headerOverlaps: 0,
    });
    expect(m.crossings).toBeLessThanOrEqual(20);
    const right = Math.max(...s.nodes.filter((n) => n.company === northwind).map((n) => n.x));
    const left = Math.min(...s.nodes.filter((n) => n.company === aurora).map((n) => n.x));
    expect(left - right).toBeGreaterThan(400);
  });

  it('lays 300 concepts out with no overlap, quickly', () => {
    const s = createScene();
    syntheticModel(s, 300);
    const t0 = performance.now();
    arrangeAll(s);
    const ms = performance.now() - t0;
    settleTweens(s);
    expect(sceneMetrics(s)).toMatchObject({ cellOverlaps: 0, hiddenLabels: 0, regionOverlaps: 0 });
    // About 250 ms on a desktop; the bound leaves room for slow test machines.
    expect(ms).toBeLessThan(3000);
  });

  it('puts a source beside the first concept bound to it and anchors it there', () => {
    const s = createScene();
    const c = northwindModel(s);
    const plant = find(s, 'Plant', c)!;
    const src = addSource(s, c, 'SAP S/4HANA', 'ERP');
    addLink(s, src, plant, 'bind', 300, 'bound to');
    arrangeAll(s);
    settleTweens(s);
    expect(src.anchor).toEqual([src.x, src.y]);
    // The source sits in the column after the concept it feeds, level with it or among its children.
    expect(Math.abs(src.x - c.x)).toBeGreaterThan(Math.abs(plant.x - c.x));
    expect(Math.sign(src.x - c.x)).toBe(Math.sign(plant.x - c.x));
    expect(s.links.some((l) => l.kind === 'bind' && l.a === src && l.b === plant)).toBe(true);
    expect(sceneMetrics(s).cellOverlaps).toBe(0);
  });

  it('hangs a cell without a living parent from its company root', () => {
    const s = createScene();
    const c = addCompany(s, 'Northwind Industries', '');
    const loose = addNode(s, { label: 'Loose', domain: domainOf(s, 'sales', c), company: c, x: 900, y: 900 });
    arrangeAll(s);
    settleTweens(s);
    expect(Math.abs(loose.y - c.y)).toBeLessThan(1);
    expect(Math.abs(loose.x - c.x)).toBeGreaterThan(100);
  });

  it('stages a lineage left to right in a clear area, with nothing crossing or covered', () => {
    const s = createScene();
    const c = northwindModel(s);
    const product = find(s, 'Product', c)!;
    const moved = staged(s, (sc) => arrangeLineage(sc, view, product));
    const restRight = Math.max(...s.nodes.filter((n) => !moved.has(n)).map((n) => n.x));
    expect(Math.min(...[...moved].map((n) => n.x))).toBeGreaterThan(restRight + 300);
    expect(sceneMetrics(s, undefined, moved)).toMatchObject({
      crossings: 0,
      cellOverlaps: 0,
      chipOverlaps: 0,
      chipsOnCells: 0,
      hiddenLabels: 0,
    });
    const plant = find(s, 'Plant', c)!;
    expect(plant.x).toBeLessThan(product.x);
    expect(find(s, 'Inspection', c)!.x).toBeGreaterThan(product.x);
  });

  it('stages a cell with what points to it on the left and what it points to on the right', () => {
    const s = createScene();
    const c = northwindModel(s);
    const order = find(s, 'Sales order', c)!;
    const moved = staged(s, (sc) => arrangeCell(sc, view, order));
    expect(find(s, 'Quotation', c)!.x).toBeLessThan(order.x);
    expect(find(s, 'Invoice', c)!.x).toBeGreaterThan(order.x);
    expect(sceneMetrics(s, undefined, moved)).toMatchObject({ crossings: 0, cellOverlaps: 0, chipOverlaps: 0, hiddenLabels: 0 });
  });

  it('stages a domain and the cells it relates to with nothing crossing', () => {
    const s = createScene();
    const c = northwindModel(s);
    const production = domainOf(s, 'production', c)!;
    const moved = staged(s, (sc) => arrangeDomain(sc, view, production));
    expect(s.domainFocus).toBe(production);
    expect(moved.has(find(s, 'Sales order', c)!)).toBe(true);
    expect(sceneMetrics(s, undefined, moved)).toMatchObject({
      crossings: 0,
      cellOverlaps: 0,
      chipOverlaps: 0,
      chipsOnCells: 0,
      hiddenLabels: 0,
    });
  });

  it('stages the highlighted set to the right of everything else', () => {
    const s = createScene();
    const c = addCompany(s, 'Northwind Industries', '');
    const production = domainOf(s, 'production', c);
    const kept = addNode(s, { label: 'Plant', domain: production, company: c, x: 300, y: 10 });
    addNode(s, { label: 'Far', domain: production, company: c, x: 900, y: -50 });
    addNode(s, { label: 'Near', domain: production, company: c, x: 100, y: 50 });
    const [sx, sy] = stageOrigin(s, new Set([kept]));
    expect(sx).toBe(900 + DOMAIN_R * 1.6);
    expect(sy).toBe(0);
    expect(stageOrigin(s, new Set(s.nodes))).toEqual([0, 0]);
  });
});
