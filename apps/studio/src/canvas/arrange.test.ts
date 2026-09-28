import { seedRandom } from '../runtime/rng';
import { arrangeAll, spiralPlacement, stageOrigin } from './arrange';
import { DOMAIN_R } from './constants';
import { addCompany, addNode, createScene, domainCentre, domainOf } from './state';

describe('arrange placement', () => {
  beforeEach(() => seedRandom(3));

  it('puts the first member of a cluster on the centre and the others on a golden-angle spiral', () => {
    expect(spiralPlacement(0, 10, 20)).toEqual([10, 20]);
    const [x, y] = spiralPlacement(1, 0, 0);
    const rr = 70 * Math.sqrt(1.5);
    expect(Math.hypot(x, y)).toBeCloseTo(rr, 9);
    expect(Math.atan2(y, x)).toBeCloseTo(2.399963, 9);
  });

  it('whole-model arrange tweens each domain member toward its spiral slot around the domain centre', () => {
    const s = createScene();
    const c = addCompany(s, 'Northwind Industries', '');
    const production = domainOf(s, 'production', c);
    const a = addNode(s, { label: 'Plant', domain: production, company: c, x: 5, y: 5 });
    const b = addNode(s, { label: 'Machine', domain: production, company: c, x: -5, y: 40 });
    arrangeAll(s);
    const [cx, cy] = domainCentre(production!);
    expect(a.tween).not.toBeNull();
    expect(b.tween).not.toBeNull();
    const targets = [a, b].map((n) => [n.tween!.tx, n.tween!.ty]);
    expect(targets).toContainEqual([cx, cy]);
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
