import { act, fireEvent, render } from '@testing-library/react';

import { api } from '../api/client';
import type { ExpansionResult, Proposal } from '../api/types';
import { addCompany, addNode, domainOf } from '../canvas/state';
import type { Company, Node } from '../canvas/types';
import { store } from '../store/store';
import { Dialog } from './Dialog';
import { Drawer } from './Drawer';
import { canExpandFromDrawer, noSuggestionsText, openExpandDialog, toggleSelection } from './ExpandDialog';
import { IMPORT_MODES, ImportModePill, importMode } from './ImportMode';
import { Panel, branchSize } from './Panel';

const flush = () => act(() => new Promise((r) => setTimeout(r, 0)));
const PAYLOAD = '<img src=x onerror=alert(1)>';

function model(): { c: Company; sales: Node } {
  const s = store.s;
  s.nodes.length = 0;
  s.links.length = 0;
  s.companies.length = 0;
  s.DOMAINS = [];
  const c = addCompany(s, 'Northwind Industries', '');
  c.sid = 'co-1';
  if (c.root) c.root.sid = 'root-1';
  const sales = addNode(s, { label: 'Sales', kind: 'concept', company: c, domain: domainOf(s, 'sales', c), parent: c.root ?? undefined, sid: 'c-sales' });
  return { c, sales };
}

const result: ExpansionResult = {
  expansionId: 'x-1',
  expiresAt: '2026-09-29T13:00:00Z',
  conceptId: 'c-sales',
  llmOutcome: 'used',
  degraded: false,
  drafts: [
    { type: 'concept', companyId: 'co-1', parentId: 'c-sales', label: 'After-sales', domainKey: 'sales', action: 'includes' },
    { type: 'concept', companyId: 'co-1', parentLabel: 'After-sales', label: 'Warranty', domainKey: 'sales', action: 'covers' },
    { type: 'concept', companyId: 'co-1', parentId: 'c-sales', label: PAYLOAD, domainKey: 'sales', action: 'has' },
    { type: 'relation', companyId: 'co-1', aLabel: 'Warranty', bId: 'c-sales', action: 'supports' },
  ],
  notes: [
    { confidence: 0.91, rationale: 'Service after the sale', depth: 1, requires: [] },
    { confidence: 0.8, rationale: 'Repairs under warranty', depth: 2, requires: [0] },
    { confidence: 0.5, rationale: PAYLOAD, depth: 1, requires: [] },
    { confidence: 0.7, rationale: 'Warranty supports sales', depth: null, requires: [1] },
  ],
  skipped: [{ label: 'Orders', reason: 'existing_label' }],
};

describe('Expand', () => {
  afterEach(() => {
    store.ui.dialogs = [];
    store.ui.drawerNode = null;
    store.ui.toasts = [];
    vi.restoreAllMocks();
  });

  it('is offered for approved concepts and the root, never for pending cells', () => {
    const { c, sales } = model();
    const pending = addNode(store.s, { label: 'Maybe', kind: 'concept', company: c, parent: sales, pending: true, sid: 'c-maybe' });
    expect(canExpandFromDrawer(sales)).toBe(true);
    expect(canExpandFromDrawer(c.root as Node)).toBe(true);
    expect(canExpandFromDrawer(pending)).toBe(false);

    store.ui.drawerNode = sales;
    const drawer = render(<Drawer />);
    const buttons = [...drawer.container.querySelectorAll('.actions button')].map((b) => b.id);
    expect(buttons.slice(-2)).toEqual(['drExpand', 'drDelete']);
    drawer.unmount();
    store.ui.drawerNode = pending;
    const waiting = render(<Drawer />);
    expect(waiting.container.querySelector('#drExpand')).toBeNull();
  });

  it('asks, lists the suggestions as text, cascades the selection and proposes the checked ones', async () => {
    const { sales } = model();
    const expand = vi.spyOn(api, 'expandConcept').mockResolvedValue(result);
    const propose = vi.spyOn(api, 'proposeExpansion').mockResolvedValue([]);
    const { container } = render(<Dialog />);
    act(() => openExpandDialog(sales));
    expect(container.querySelector('.dlg .dh b')?.textContent).toBe('Expand Sales');
    expect(container.querySelector('.dlg .dh span')?.textContent).toBe('The model suggests concepts to grow from it; each one is a proposal');
    expect([...container.querySelectorAll('#exDepth option')].map((o) => o.textContent)).toEqual(['Any depth', '1', '2', '3', '4', '5']);
    expect(container.querySelector<HTMLInputElement>('#exFocus')?.maxLength).toBe(200);
    expect(container.querySelector<HTMLInputElement>('#exFocus')?.placeholder).toBe('e.g. after-sales services');

    fireEvent.change(container.querySelector('#exDepth') as HTMLSelectElement, { target: { value: '2' } });
    fireEvent.change(container.querySelector('#exFocus') as HTMLInputElement, { target: { value: 'after-sales services' } });
    fireEvent.click(container.querySelector('.dlg .df .btn.primary') as HTMLButtonElement);
    await flush();
    expect(expand).toHaveBeenCalledWith('c-sales', expect.objectContaining({ depth: 2, focus: 'after-sales services' }));

    expect(container.querySelector('.dlg .dh span')?.textContent).toBe('4 suggestions · 1 skipped');
    const rows = [...container.querySelectorAll('.dlg .chk')];
    expect(rows.map((r) => r.querySelector('b')?.textContent)).toEqual(['After-sales', 'Warranty', PAYLOAD, 'Warranty supports Sales']);
    expect(rows[1].querySelector('.ex-verb')?.textContent).toBe('covers After-sales');
    expect(rows[1].querySelector('.ex-conf')?.textContent).toBe('80%');
    expect(rows[1].querySelector('small')?.textContent).toBe('level 2 · Repairs under warranty');
    expect(rows[3].querySelector('.ex-verb')?.textContent).toBe('relation');
    expect(container.querySelector('.dlg img')).toBeNull();
    const boxes = () => [...container.querySelectorAll<HTMLInputElement>('.dlg .chk input')].map((b) => b.checked);
    const primary = () => container.querySelector('.dlg .df .btn.primary') as HTMLButtonElement;
    expect(boxes()).toEqual([true, true, true, true]);
    expect(primary().textContent).toBe('Propose 4');

    fireEvent.click(rows[0].querySelector('input') as HTMLInputElement);
    expect(boxes()).toEqual([false, false, true, false]);
    expect(primary().textContent).toBe('Propose 1');
    fireEvent.click(rows[3].querySelector('input') as HTMLInputElement);
    expect(boxes()).toEqual([true, true, true, true]);
    fireEvent.click(rows[2].querySelector('input') as HTMLInputElement);
    fireEvent.click(primary());
    await flush();
    expect(propose).toHaveBeenCalledWith('x-1', [0, 1, 3]);
    expect(container.querySelector('.dlg')).toBeNull();
  });

  it('lays the suggestions out as a full-width list with aligned label, link and confidence columns', async () => {
    const { sales } = model();
    vi.spyOn(api, 'expandConcept').mockResolvedValue(result);
    const { container } = render(<Dialog />);
    act(() => openExpandDialog(sales));
    fireEvent.click(container.querySelector('.dlg .df .btn.primary') as HTMLButtonElement);
    await flush();

    const list = container.querySelector('.dlg .db > .ex-list') as HTMLElement;
    expect(list).not.toBeNull();
    expect(list.closest('.form')).toBeNull();
    expect(list.getAttribute('role')).toBe('group');
    expect([...list.querySelectorAll('.ex-head span')].map((s) => s.textContent)).toEqual(['', 'Suggestion', 'Link', 'Confidence']);
    const rows = [...list.querySelectorAll('label.chk.ex-row')];
    expect(rows).toHaveLength(4);
    for (const row of rows)
      expect([...row.children].map((c) => c.className || c.tagName.toLowerCase())).toEqual(['input', 'ex-label', 'ex-verb', 'ex-conf', 'ex-note']);
    expect(rows.map((r) => r.querySelector('.ex-conf')?.textContent)).toEqual(['91%', '80%', '50%', '70%']);
    expect(rows[0].querySelector('.ex-note')?.textContent).toBe('level 1 · Service after the sale');
    expect(rows[3].querySelector('.ex-note')?.textContent).toBe('Warranty supports sales');
  });

  it('closes with a toast when nothing is suggested', async () => {
    const { sales } = model();
    vi.spyOn(api, 'expandConcept').mockResolvedValue({ ...result, expansionId: null, expiresAt: null, llmOutcome: 'refused', degraded: true, drafts: [], notes: [], skipped: [] });
    const { container } = render(<Dialog />);
    act(() => openExpandDialog(sales));
    fireEvent.click(container.querySelector('.dlg .df .btn.primary') as HTMLButtonElement);
    await flush();
    expect(container.querySelector('.dlg')).toBeNull();
    expect(store.ui.toasts.map((t) => [t.strong, t.text])).toEqual([['No suggestions', 'The model declined this request']]);
    expect(noSuggestionsText('timeout')).toBe('The model is not available');
    expect(noSuggestionsText('invalid_output')).toBe('The model is not available');
    expect(noSuggestionsText('budget_exhausted')).toBe('The model budget is spent');
    expect(noSuggestionsText('rate_limited')).toBe('The model budget is spent');
    expect(noSuggestionsText('used')).toBe('Everything suggested is already in the model');
  });

  it('keeps a selection closed under what each draft requires', () => {
    const requires = [[], [0], [1], [0, 2]];
    expect([...toggleSelection(new Set([0, 1, 2, 3]), requires, 1)].sort()).toEqual([0]);
    expect([...toggleSelection(new Set([0]), requires, 3)].sort()).toEqual([0, 1, 2, 3]);
  });
});

describe('Approve branch', () => {
  const proposal = (over: Partial<Proposal>): Proposal => ({
    id: 'p-1',
    type: 'concept',
    state: 'pending',
    title: 'After-sales',
    heading: 'New concept · Sales · suggested',
    color: '#fff',
    deps: [],
    ready: true,
    html: '<b>After-sales</b>',
    why: 'Suggested by the model · 91% · Service after the sale',
    relationIds: [],
    bindingIds: [],
    proposer: { kind: 'user' },
    origin: 'suggestion',
    originDetail: null,
    approvals: [],
    createdAt: '2026-09-29T12:00:00Z',
    ...over,
  });

  afterEach(() => {
    store.ui.proposals = [];
    vi.restoreAllMocks();
  });

  it('shows on ready concept and spec proposals with open proposals below, counting the root', () => {
    expect(branchSize(proposal({ openBelow: 3 }))).toBe(4);
    expect(branchSize(proposal({ openBelow: 0 }))).toBe(0);
    expect(branchSize(proposal({ openBelow: 2, ready: false }))).toBe(0);
    expect(branchSize(proposal({ openBelow: 2, type: 'relation' }))).toBe(0);
    expect(branchSize(proposal({ openBelow: 2, type: 'spec' }))).toBe(3);

    store.ui.proposals = [proposal({ openBelow: 2 }), proposal({ id: 'p-2', openBelow: 0 })];
    const { container } = render(<Panel />);
    const rows = [...container.querySelectorAll('.prop')];
    expect([...rows[0].querySelectorAll('.act button')].map((b) => b.textContent)).toEqual(['Approve', 'Reject', 'Approve branch (3)']);
    expect(rows[1].querySelectorAll('.act button')).toHaveLength(2);
    expect(rows[0].querySelector('.top')?.textContent).toBe('New concept · Sales · suggested');
    expect(rows[0].querySelector('.why')?.textContent).toBe('Suggested by the model · 91% · Service after the sale');
  });

  it('calls again on the same root while the branch is incomplete and progressing', async () => {
    vi.spyOn(api, 'listProposals').mockResolvedValue({ items: [], page: 1, pageSize: 1, total: 0 });
    const branch = vi
      .spyOn(api, 'approveBranch')
      .mockResolvedValueOnce({ rootId: 'p-1', approved: 200, skipped: 0, remaining: 5, batches: 50, complete: false })
      .mockResolvedValueOnce({ rootId: 'p-1', approved: 5, skipped: 0, remaining: 0, batches: 1, complete: true });
    await store.approveBranch(proposal({ openBelow: 204 }));
    expect(branch).toHaveBeenCalledTimes(2);
    expect(branch).toHaveBeenLastCalledWith('p-1');
  });
});

describe('Import mode', () => {
  it('cycles Sentences, Whole document and Ontology on one pill, Sentences by default', () => {
    const { container } = render(<ImportModePill hidden={false} />);
    const pill = container.querySelector<HTMLButtonElement>('#imMode');
    if (!pill) throw new Error('no #imMode pill');
    const seen = () => [pill.textContent, pill.getAttribute('aria-pressed'), importMode()];
    expect(IMPORT_MODES.map((m) => m.label)).toEqual(['Sentences', 'Whole document', 'Ontology']);
    expect(seen()).toEqual(['Sentences', 'false', 'sentences']);
    fireEvent.click(pill);
    expect(seen()).toEqual(['Whole document', 'true', 'document']);
    fireEvent.click(pill);
    expect(seen()).toEqual(['Ontology', 'true', 'ontology']);
    fireEvent.click(pill);
    expect(seen()).toEqual(['Sentences', 'false', 'sentences']);
  });
});
