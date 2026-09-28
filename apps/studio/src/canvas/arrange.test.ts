import { mulberry32 } from '../runtime/mulberry32';
import { setSource } from '../runtime/rng';
import { arrangeAll, stageOrigin } from './arrange';
import { DOMAIN_R } from './constants';
import { addCompany, addNode, createScene, domainCentre, domainOf } from './state';

describe('arrange placement', () => {
  beforeEach(() => setSource(mulberry32(3)));
  afterEach(() => setSource(null));

  it('whole-model arrange puts the first member on the domain centre and the next on the golden-angle spiral', () => {
    const s = createScene();
    const c = addCompany(s, 'Northwind Industries', '');
    const production = domainOf(s, 'production', c);
    const a = addNode(s, { label: 'Plant', domain: production, company: c, x: 5, y: 5 });
    const b = addNode(s, { label: 'Machine', domain: production, company: c, x: -5, y: 40 });
    arrangeAll(s);
    const [cx, cy] = domainCentre(production!);
    expect(a.tween).toMatchObject({ tx: cx, ty: cy });
    const rr = 70 * Math.sqrt(1.5);
    expect(Math.hypot(b.tween!.tx - cx, b.tween!.ty - cy)).toBeCloseTo(rr, 9);
    expect(Math.atan2(b.tween!.ty - cy, b.tween!.tx - cx)).toBeCloseTo(2.399963, 9);
    expect(s.cam.tx).toBe(0);
    expect(s.userZoomed).toBe(false);
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
