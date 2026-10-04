import { render } from '@testing-library/react';

import { DOMAIN_TEMPLATES } from '../canvas/constants';
import { addCompany, addNode, domainOf } from '../canvas/state';
import { store } from '../store/store';
import { NewBox } from './Boxes';
import { DomainsCard } from './DomainsCard';

/** Two companies on the canvas, each with the nine template domains, so every domain key appears twice. */
function twoCompanies(): void {
  const s = store.s;
  s.nodes.length = 0;
  s.links.length = 0;
  s.companies.length = 0;
  s.DOMAINS = [];
  s.selected.clear();
  store.ui.newBox = null;
  store.ui.domains = DOMAIN_TEMPLATES.map((t, position) => ({ key: t.key, name: t.name, owner: t.owner, color: t.color, defaultColor: t.color, template: true, position, revision: 0 }));
  const a = addCompany(s, 'Northwind Industries', '');
  a.sid = 'co-1';
  addNode(s, { label: 'Plant', kind: 'concept', company: a, domain: domainOf(s, 'production', a), parent: a.root ?? undefined, sid: 'c-plant' });
  const b = addCompany(s, 'Aurora Mobility', '');
  b.sid = 'co-2';
  addNode(s, { label: 'Depot', kind: 'concept', company: b, domain: domainOf(s, 'production', b), parent: b.root ?? undefined, sid: 'c-depot' });
}

describe('two companies sharing domain keys', () => {
  it('render their domain lists without a duplicate-key warning', () => {
    twoCompanies();
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      const { container } = render(
        <>
          <NewBox />
          <DomainsCard />
        </>,
      );
      expect(container.querySelectorAll('#nbDomain option')).toHaveLength(DOMAIN_TEMPLATES.length * 2);
      expect(container.querySelectorAll('#domains .co')).toHaveLength(2);
      const duplicates = error.mock.calls.filter((args) => args.some((a) => typeof a === 'string' && a.includes('same key')));
      expect(duplicates).toEqual([]);
    } finally {
      error.mockRestore();
    }
  });
});
