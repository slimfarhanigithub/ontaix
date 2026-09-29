import { render } from '@testing-library/react';

import { addCompany, addNode, domainOf } from '../canvas/state';
import type { Attr } from '../canvas/types';
import { store } from '../store/store';
import { Drawer } from './Drawer';

describe('drawer attributes', () => {
  afterEach(() => {
    store.ui.drawerNode = null;
  });

  function drawerWith(attrs: Attr[]): HTMLElement {
    const s = store.s;
    s.nodes.length = 0;
    s.links.length = 0;
    s.companies.length = 0;
    const c = addCompany(s, 'Insight', 'IT services');
    const n = addNode(s, { label: 'Managed services', kind: 'concept', company: c, domain: domainOf(s, 'sales', c) });
    n.attrs = attrs;
    store.ui.drawerNode = n;
    return render(<Drawer />).container;
  }

  it('shows a taught value in the column line, with no fill bar', () => {
    const container = drawerWith([
      { sid: 'a1', name: 'billing', type: 'text', col: '', fill: 0, value: 'monthly', state: 'approved' },
      { sid: 'a2', name: 'matnr', type: 'id', col: 'sap.mara.matnr', fill: 98, state: 'proposed' },
    ]);
    const [taught, read] = Array.from(container.querySelectorAll('#drAttrs .attr'));
    expect(taught.querySelector('b')?.textContent).toBe('billing');
    expect(taught.querySelector('.col')?.textContent).toBe('text · monthly');
    expect(taught.querySelector('.fill')).toBeNull();
    expect(taught.querySelector('.state')?.textContent).toBe('approved');
    expect(taught.children).toHaveLength(3);
    // An attribute read from a source keeps its column and fill bar.
    expect(read.querySelector('.col')?.textContent).toBe('id · sap.mara.matnr');
    expect(read.querySelector('.fill i')?.getAttribute('style')).toContain('width: 98%');
    expect(read.querySelector('.state.new')?.textContent).toBe('found in data · pending');
  });

  it('renders a taught value as text', () => {
    const payload = '<img src=x onerror=alert(1)>';
    const container = drawerWith([{ sid: 'a1', name: 'billing', type: 'text', col: '', fill: 0, value: payload, state: 'proposed' }]);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('#drAttrs .col')?.textContent).toBe(`text · ${payload}`);
  });
});
