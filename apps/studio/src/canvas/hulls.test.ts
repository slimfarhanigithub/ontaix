import { mulberry32 } from '../runtime/mulberry32';
import { setSource } from '../runtime/rng';
import { hitDomainAt, hull, inHull } from './hulls';
import { addCompany, addNode, createScene, domainOf } from './state';

describe('hull', () => {
  it('returns fewer than three points unchanged', () => {
    expect(hull([[0, 0]])).toEqual([[0, 0]]);
  });

  it('drops interior points and keeps the convex outline', () => {
    const h = hull([
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
      [5, 5],
    ]);
    expect(h).toHaveLength(4);
    expect(h).not.toContainEqual([5, 5]);
    expect(inHull(h, 5, 5)).toBe(true);
    expect(inHull(h, 20, 5)).toBe(false);
  });
});

describe('hitDomain nearest-cell rule', () => {
  beforeEach(() => setSource(mulberry32(1)));
  afterEach(() => setSource(null));

  it('picks the domain whose nearest member is closest when two padded shapes overlap', () => {
    const s = createScene();
    const c = addCompany(s, 'Northwind Industries', '');
    const production = domainOf(s, 'production', c);
    const sales = domainOf(s, 'sales', c);
    // Two members of Production at x = 0 and 100, one Sales member at x = 160: their 86 px
    // paddings overlap between x = 100 and 160.
    addNode(s, { label: 'Plant', domain: production, company: c, x: 0, y: 0 });
    addNode(s, { label: 'Machine', domain: production, company: c, x: 100, y: 0 });
    addNode(s, { label: 'Customer', domain: sales, company: c, x: 160, y: 0 });
    expect(hitDomainAt(s, 120, 0)).toBe(production);
    expect(hitDomainAt(s, 140, 0)).toBe(sales);
    // An exact tie (30 px to either) keeps the first domain in ring order.
    expect(hitDomainAt(s, 130, 0)).toBe(production);
    expect(hitDomainAt(s, 135, 0)).toBe(sales);
  });

  it('ignores hidden domains and empty space beyond the padding', () => {
    const s = createScene();
    const c = addCompany(s, 'Northwind Industries', '');
    const production = domainOf(s, 'production', c);
    addNode(s, { label: 'Plant', domain: production, company: c, x: 0, y: 0 });
    expect(hitDomainAt(s, 0, 86)).toBe(production);
    expect(hitDomainAt(s, 0, 87)).toBeNull();
    if (production) production.hidden = true;
    expect(hitDomainAt(s, 0, 0)).toBeNull();
  });
});
