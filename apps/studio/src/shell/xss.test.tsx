import { render, screen } from '@testing-library/react';

import type { Proposal } from '../api/types';
import { addCompany, addNode, domainOf } from '../canvas/state';
import { store } from '../store/store';
import { Drawer } from './Drawer';
import { Panel } from './Panel';
import { sanitizeHtml } from './sanitize';
import { Toasts } from './Toasts';

const PAYLOAD = '<img src=x onerror=alert(1)>';

const proposal = (html: string): Proposal => ({
  id: 'p1',
  type: 'concept',
  state: 'pending',
  title: PAYLOAD,
  heading: 'New concept · Production',
  color: '#3fb8a9',
  deps: [],
  ready: true,
  html,
  relationIds: [],
  bindingIds: [],
  proposer: { kind: 'user' },
  approvals: [],
  createdAt: '2026-09-28T09:00:00Z',
});

describe('user text never becomes markup', () => {
  afterEach(() => {
    store.ui.proposals = [];
    store.ui.toasts = [];
    store.ui.drawerNode = null;
  });

  it('sanitiser keeps b, i, em and span.class and escapes everything else', () => {
    expect(sanitizeHtml(`<b>Plant</b> <em>· x <b>runs</b> y</em>`)).toBe('<b>Plant</b> <em>· x <b>runs</b> y</em>');
    expect(sanitizeHtml(`<span class="k" onclick="alert(1)">a</span>`)).toBe('<span class="k">a</span>');
    expect(sanitizeHtml(`<b onmouseover="alert(1)">a</b>`)).toBe('<b>a</b>');
    const out = sanitizeHtml(`<b>${PAYLOAD}</b>`);
    expect(out).not.toContain('<img');
    expect(out).toContain('&lt;img');
    expect(sanitizeHtml('<script>alert(1)</script>')).toBe('&lt;script&gt;alert(1)&lt;/script&gt;');
  });

  it('panel rows render an injected label as text', () => {
    store.ui.proposals = [proposal(`<b>${PAYLOAD}</b> <em>· root <b>has</b> ${PAYLOAD}</em>`)];
    const { container } = render(<Panel />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('.what')?.innerHTML).not.toContain('<img');
    // The disallowed tag survives only as literal text, stripped of its attributes.
    expect(container.querySelector('.what')?.textContent).toBe('<img></img> · root has <img></img>');
  });

  it('toasts render their text as text', () => {
    store.toast2('Approved', PAYLOAD);
    const { container } = render(<Toasts />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText(PAYLOAD)).toBeInTheDocument();
  });

  it('drawer meta renders labels, subs and company names as text', () => {
    const s = store.s;
    s.nodes.length = 0;
    s.links.length = 0;
    s.companies.length = 0;
    const c = addCompany(s, PAYLOAD, PAYLOAD);
    const n = addNode(s, { label: PAYLOAD, sub: PAYLOAD, kind: 'concept', company: c, domain: domainOf(s, 'production', c) });
    store.ui.drawerNode = n;
    const { container } = render(<Drawer />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('#drName')?.textContent).toBe(`${PAYLOAD} · ${PAYLOAD}`);
    store.ui.drawerNode = c.root;
    const root = render(<Drawer />);
    expect(root.container.querySelector('img')).toBeNull();
    expect(root.container.querySelector('#drMeta')?.textContent).toContain(PAYLOAD);
  });
});
