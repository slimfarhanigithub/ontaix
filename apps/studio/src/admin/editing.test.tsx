import { act, fireEvent, render } from '@testing-library/react';

import { api } from '../api/client';
import type { DeletionImpact, Proposal, TenantDomain } from '../api/types';
import { DOMAIN_TEMPLATES } from '../canvas/constants';
import { addCompany, addNode, domainOf } from '../canvas/state';
import type { Company, Node } from '../canvas/types';
import { Dialog } from '../shell/Dialog';
import { store } from '../store/store';
import { bulkWhat, deleteDomainDialog, editDomainDialog, newDomainDialog, removeCompanyDialog } from './actions';
import { impactText } from './conceptDeletion';
import { Companies, DomainProducts, Entities } from './pages/ModelPages';
import { Appearance, TenantSettings } from './pages/PortalPages';

const flush = () => act(() => new Promise((r) => setTimeout(r, 0)));

const settings = {
  voice: true,
  importDocs: true,
  liveTeaching: true,
  everyoneTeaches: false,
  approvalRequired: true as const,
  twoApprovers: false,
  autoAttrs: false,
  notifyOwners: true,
  multiCompany: true,
  companyCreation: true,
  crossCompany: true,
  animations: true,
  coverageDefault: false,
  legend: true,
  readOnlyConnectors: true as const,
  refresh: '15 min' as const,
  agentAccess: true,
  costCap: true,
  llmMonthlyTokenCap: 2_000_000,
  ocrMonthlyPageCap: 1000,
};

const templates = (): TenantDomain[] =>
  DOMAIN_TEMPLATES.map((t, position) => ({ key: t.key, name: t.name, owner: t.owner, color: t.color, defaultColor: t.color, template: true, position, revision: 0 }));

function model(): { a: Company; b: Company; plant: Node; line: Node; valve: Node } {
  const s = store.s;
  s.nodes.length = 0;
  s.links.length = 0;
  s.companies.length = 0;
  s.DOMAINS = [];
  s.selected.clear();
  store.ui.domains = templates();
  store.ui.settings = { ...settings };
  store.ui.appearance = { theme: 'dark', colors: {}, accent: '#3fb8a9', source: '#d6bd8a', defaults: { colors: {}, accent: '#3fb8a9', source: '#d6bd8a' } };
  const a = addCompany(s, 'Northwind Industries', '');
  a.sid = 'co-1';
  const production = domainOf(s, 'production', a);
  if (production) production.sid = 'dp-1';
  const plant = addNode(s, { label: 'Plant', kind: 'concept', company: a, domain: production, parent: a.root ?? undefined, sid: 'c-plant' });
  const line = addNode(s, { label: 'Line', kind: 'concept', company: a, domain: production, parent: plant, sid: 'c-line' });
  const b = addCompany(s, 'Aurora Valves', 'valves');
  b.sid = 'co-2';
  const bProduction = domainOf(s, 'production', b);
  if (bProduction) bProduction.sid = 'dp-2';
  const valve = addNode(s, { label: 'Valve', kind: 'concept', company: b, domain: bProduction, parent: b.root ?? undefined, sid: 'c-valve' });
  return { a, b, plant, line, valve };
}

const change = (kind: string): Proposal => ({ id: 'p9', type: 'change', changeKind: kind, state: 'pending', title: kind }) as unknown as Proposal;

const impact = (extra: Partial<DeletionImpact> = {}): DeletionImpact => ({
  concepts: 3,
  descendants: 2,
  relations: 5,
  crossCompanyRelations: 1,
  bindings: 2,
  attributes: 4,
  sources: 1,
  cascadedProposals: 2,
  names: ['A', 'B', 'C', 'D', 'E'],
  ...extra,
});

describe('deletion impact text', () => {
  it('names everything that goes, in the style of concept deletion', () => {
    expect(impactText(impact(), true)).toBe(
      'Its 3 concepts (A, B, C, D, E), 2 descendants, 5 relations (1 across companies), 1 source, 2 bindings and 4 attributes go with it. 2 open proposals are rejected with them. This proposes a change for approval.',
    );
    expect(impactText(impact({ concepts: 1, descendants: 0, relations: 1, crossCompanyRelations: 0, bindings: 0, attributes: 1, cascadedProposals: 1, names: ['Valve'] }), false)).toBe(
      'Its 1 concept (Valve), 0 descendants, 1 relation, 0 bindings and 1 attribute go with it. 1 open proposal is rejected with them. This proposes a change for approval.',
    );
    expect(impactText(impact({ concepts: 8, descendants: 1, names: ['A', 'B', 'C', 'D', 'E', 'F'], cascadedProposals: 0 }), false)).toBe(
      'Its 8 concepts (A, B, C, D, E, F and 3 more), 1 descendant, 5 relations (1 across companies), 2 bindings and 4 attributes go with it. This proposes a change for approval.',
    );
    expect(impactText(impact({ concepts: 0, descendants: 0, names: [], relations: 0, crossCompanyRelations: 0, bindings: 0, attributes: 0, sources: 0, cascadedProposals: 0 }), true)).toBe(
      'Its 0 concepts, 0 descendants, 0 relations, 0 sources, 0 bindings and 0 attributes go with it. This proposes a change for approval.',
    );
    expect(bulkWhat(3, 1)).toBe('3 concepts and 1 domain product');
    expect(bulkWhat(1, 0)).toBe('1 concept');
    expect(bulkWhat(0, 2)).toBe('2 domain products');
  });
});

describe('company removal', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.dialogs = [];
    store.ui.toasts = [];
  });

  it('reads the impact of the whole company, confirms with it, then proposes the removal; the home company has no Remove', async () => {
    const { b } = model();
    const read = vi.spyOn(api, 'deletionImpact').mockResolvedValue(impact({ names: ['Valve', '<img src=x onerror=alert(1)>'] }));
    const remove = vi.spyOn(api, 'proposeRemoveCompany').mockResolvedValue(change('remove_company'));
    const dialog = render(<Dialog />);
    const page = render(<Companies />);
    const buttons = page.container.querySelectorAll('[data-act="removeCompany"]');
    expect(buttons).toHaveLength(1);
    expect(page.container.querySelector('[data-act="addCompany"]')).not.toBeNull();
    act(() => (buttons[0] as HTMLButtonElement).click());
    await flush();
    expect(read).toHaveBeenCalledWith({ companyId: 'co-2', wholeCompany: true });
    const dlg = dialog.container.querySelector('.dlg');
    expect(dlg?.querySelector('.dh b')?.textContent).toBe('Remove Aurora Valves?');
    expect(dlg?.querySelector('.db')?.textContent).toBe(
      'Its 3 concepts (Valve, <img src=x onerror=alert(1)> and 3 more), 2 descendants, 5 relations (1 across companies), 1 source, 2 bindings and 4 attributes go with it. 2 open proposals are rejected with them. This proposes a change for approval.',
    );
    expect(dlg?.querySelector('img')).toBeNull();
    const yes = dlg?.querySelector('.df .btn.danger') as HTMLButtonElement;
    expect(yes.textContent).toBe('Propose removal');
    act(() => yes.click());
    await flush();
    expect(remove).toHaveBeenCalledWith('co-2');
    expect(store.ui.toasts.map((t) => t.text)).toEqual(['removal of Aurora Valves · approve it on the canvas']);
    expect(b.sid).toBe('co-2');
  });

  it('a refused impact read shows the toast and opens nothing', async () => {
    const { b } = model();
    const { ApiError } = await import('../api/types');
    vi.spyOn(api, 'deletionImpact').mockRejectedValue(new ApiError(403, { title: 'Forbidden', status: 403, code: 'forbidden', detail: 'not yours' }));
    await removeCompanyDialog(b);
    expect(store.ui.dialogs).toHaveLength(0);
    expect(store.ui.toasts.map((t) => [t.strong, t.text])).toEqual([['Refused', 'not yours']]);
  });
});

describe('domains', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.dialogs = [];
    store.ui.toasts = [];
  });

  it('New domain proposes name, owner and colour', async () => {
    model();
    const create = vi.spyOn(api, 'proposeCreateDomain').mockResolvedValue(change('create_domain'));
    const dialog = render(<Dialog />);
    const page = render(<DomainProducts />);
    act(() => page.container.querySelector<HTMLButtonElement>('[data-act="newDomain"]')?.click());
    const dlg = dialog.container.querySelector('.dlg');
    expect(dlg?.querySelector('.dh b')?.textContent).toBe('New domain');
    expect(dlg?.querySelector('.col input[type="color"]')).not.toBeNull();
    fireEvent.change(dlg?.querySelector('#dmName') as HTMLInputElement, { target: { value: 'Sustainability' } });
    fireEvent.change(dlg?.querySelector('#dmOwner') as HTMLInputElement, { target: { value: 'Facilities' } });
    fireEvent.change(dlg?.querySelector('#dmColor') as HTMLInputElement, { target: { value: '#112233' } });
    act(() => (dlg?.querySelectorAll('.df .btn')[1] as HTMLButtonElement).click());
    await flush();
    expect(create).toHaveBeenCalledWith({ name: 'Sustainability', owner: 'Facilities', color: '#112233' });
    expect(store.ui.toasts.map((t) => t.text)).toEqual(['new domain Sustainability · approve it on the canvas']);
  });

  it('Edit sends only what changed; an unchanged form stays open', async () => {
    model();
    const edit = vi.spyOn(api, 'proposeEditDomain').mockResolvedValue(change('edit_domain'));
    const dialog = render(<Dialog />);
    act(() => editDomainDialog(store.ui.domains[0]));
    const dlg = dialog.container.querySelector('.dlg');
    expect(dlg?.querySelector('.dh b')?.textContent).toBe('Edit Production');
    expect((dlg?.querySelector('#dmName') as HTMLInputElement).value).toBe('Production');
    act(() => (dlg?.querySelectorAll('.df .btn')[1] as HTMLButtonElement).click());
    await flush();
    expect(edit).not.toHaveBeenCalled();
    expect(store.ui.dialogs).toHaveLength(1);
    fireEvent.change(dlg?.querySelector('#dmName') as HTMLInputElement, { target: { value: 'Manufacturing' } });
    fireEvent.change(dlg?.querySelector('#dmColor') as HTMLInputElement, { target: { value: '#abcdef' } });
    act(() => (dlg?.querySelectorAll('.df .btn')[1] as HTMLButtonElement).click());
    await flush();
    expect(edit).toHaveBeenCalledWith('production', { name: 'Manufacturing', color: '#abcdef' });
    expect(store.ui.dialogs).toHaveLength(0);
  });

  it('Delete confirms with the impact of one domain product and proposes its deletion', async () => {
    const { a } = model();
    const read = vi.spyOn(api, 'deletionImpact').mockResolvedValue(impact({ concepts: 2, descendants: 0, names: ['Plant', 'Line'], cascadedProposals: 0 }));
    const del = vi.spyOn(api, 'proposeDeleteDomain').mockResolvedValue(change('delete_domain'));
    const dialog = render(<Dialog />);
    await act(() => deleteDomainDialog(a.domains[0]));
    expect(read).toHaveBeenCalledWith({ companyId: 'co-1', domainProductIds: ['dp-1'] });
    const dlg = dialog.container.querySelector('.dlg');
    expect(dlg?.querySelector('.dh b')?.textContent).toBe('Delete Production of Northwind Industries?');
    expect(dlg?.querySelector('.db')?.textContent).toBe(
      'Its 2 concepts (Plant, Line), 0 descendants, 5 relations (1 across companies), 2 bindings and 4 attributes go with it. This proposes a change for approval.',
    );
    act(() => (dlg?.querySelector('.df .btn.danger') as HTMLButtonElement).click());
    await flush();
    expect(del).toHaveBeenCalledWith('dp-1');
  });

  it('the Domain products page marks its additions, lists idle tenant domains, and bulk-deletes picked products', async () => {
    model();
    store.ui.domains = [...templates(), { key: 'sustainability', name: 'Sustainability', owner: 'Facilities', color: '#112233', defaultColor: '#112233', template: false, position: 9, revision: 0 }];
    const read = vi.spyOn(api, 'deletionImpact').mockResolvedValue(impact({ cascadedProposals: 0 }));
    const bulk = vi.spyOn(api, 'proposeBulkDelete').mockResolvedValue(change('delete_bulk'));
    const dialog = render(<Dialog />);
    const page = render(<DomainProducts />);
    const heads = Array.from(page.container.querySelectorAll('thead th'));
    expect(heads.map((h) => h.textContent)).toEqual(['Select', 'Company', 'Domain product', 'Owner', 'Version', 'Concepts', 'Bound', 'Visible', '']);
    expect(heads[0].getAttribute('data-ox-new')).toBe('');
    expect(heads[8].getAttribute('data-ox-new')).toBe('');
    const rows = Array.from(page.container.querySelectorAll('tbody tr'));
    // Two products with cells, then every tenant domain without cells (eight templates and the custom one).
    expect(rows).toHaveLength(2 + 9);
    expect(rows[0].querySelector('td[data-ox-new] input[type="checkbox"]')).not.toBeNull();
    expect(rows[0].querySelector('td.act[data-ox-new]')?.textContent).toBe('EditDelete');
    const idle = rows.find((r) => r.textContent?.includes('Sustainability'));
    expect(idle?.getAttribute('data-ox-new')).toBe('');
    expect(idle?.querySelector('.act')?.textContent).toBe('Edit');
    const deleteSelected = page.container.querySelector<HTMLButtonElement>('#domDeleteSelected') as HTMLButtonElement;
    expect(deleteSelected.textContent).toBe('Delete selected (0)');
    expect(deleteSelected.disabled).toBe(true);
    fireEvent.click(rows[0].querySelector('input[type="checkbox"]') as HTMLInputElement);
    expect(page.container.querySelector('#domDeleteSelected')?.textContent).toBe('Delete selected (1)');
    act(() => page.container.querySelector<HTMLButtonElement>('#domDeleteSelected')?.click());
    await flush();
    expect(read).toHaveBeenCalledWith({ companyId: 'co-1', conceptIds: [], domainProductIds: ['dp-1'] });
    expect(dialog.container.querySelector('.dlg .dh b')?.textContent).toBe('Delete 1 domain product?');
    act(() => (dialog.container.querySelector('.dlg .df .btn.danger') as HTMLButtonElement).click());
    await flush();
    expect(bulk).toHaveBeenCalledWith({ companyId: 'co-1', conceptIds: [], domainProductIds: ['dp-1'] });
  });

  it('Appearance shows a colour input per custom domain, marked as an addition', () => {
    model();
    store.ui.domains = [...templates(), { key: 'sustainability', name: 'Sustainability', owner: 'Facilities', color: '#112233', defaultColor: '#112233', template: false, position: 9, revision: 0 }];
    const { container } = render(<Appearance />);
    const cols = Array.from(container.querySelectorAll('.colors .col'));
    expect(cols).toHaveLength(9 + 1 + 2);
    const custom = cols[9];
    expect(custom.getAttribute('data-ox-new')).toBe('');
    expect(custom.querySelector('b')?.textContent).toBe('Sustainability');
    expect((custom.querySelector('input') as HTMLInputElement).value).toBe('#112233');
    expect(cols[0].getAttribute('data-ox-new')).toBeNull();
  });
});

describe('Entities additions', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.dialogs = [];
    store.ui.toasts = [];
  });

  it('has a checkbox column, Move per row and Delete selected, each marked as an addition; a pick across companies is explained', async () => {
    model();
    const read = vi.spyOn(api, 'deletionImpact').mockResolvedValue(impact({ cascadedProposals: 0 }));
    const bulk = vi.spyOn(api, 'proposeBulkDelete').mockResolvedValue(change('delete_bulk'));
    const dialog = render(<Dialog />);
    const page = render(<Entities />);
    const heads = Array.from(page.container.querySelectorAll('thead th'));
    expect(heads[0].textContent).toBe('Select');
    expect(heads[0].getAttribute('data-ox-new')).toBe('');
    const rows = Array.from(page.container.querySelectorAll('tbody tr'));
    expect(rows).toHaveLength(3);
    expect(rows[0].querySelector('td[data-ox-new] input[type="checkbox"]')?.getAttribute('aria-label')).toBe('Select Plant');
    expect(rows[0].querySelector('button[data-fn="move"]')?.getAttribute('data-ox-new')).toBe('');
    expect(Array.from(rows[0].querySelectorAll('td.act button')).map((b) => b.textContent)).toEqual(['Open', 'Lineage', 'Rename', 'Move', 'Delete']);
    const button = () => page.container.querySelector<HTMLButtonElement>('#entDeleteSelected') as HTMLButtonElement;
    expect(button().closest('[data-ox-new]')).not.toBeNull();
    expect(button().disabled).toBe(true);
    fireEvent.click(rows[0].querySelector('input[type="checkbox"]') as HTMLInputElement);
    fireEvent.click(rows[2].querySelector('input[type="checkbox"]') as HTMLInputElement);
    expect(button().textContent).toBe('Delete selected (2)');
    act(() => button().click());
    await flush();
    expect(read).not.toHaveBeenCalled();
    expect(store.ui.toasts.map((t) => t.strong)).toEqual(['One company at a time']);
    fireEvent.click(rows[2].querySelector('input[type="checkbox"]') as HTMLInputElement);
    fireEvent.click(rows[1].querySelector('input[type="checkbox"]') as HTMLInputElement);
    act(() => button().click());
    await flush();
    expect(read).toHaveBeenCalledWith({ companyId: 'co-1', conceptIds: ['c-plant', 'c-line'], domainProductIds: [] });
    expect(dialog.container.querySelector('.dlg .dh b')?.textContent).toBe('Delete 2 concepts?');
    act(() => (dialog.container.querySelector('.dlg .df .btn.danger') as HTMLButtonElement).click());
    await flush();
    expect(bulk).toHaveBeenCalledWith({ companyId: 'co-1', conceptIds: ['c-plant', 'c-line'], domainProductIds: [] });
    // Move opens the drawer's move dialog (the list re-rendered after the proposal, so the rows are read again).
    act(() => (page.container.querySelector('tbody tr button[data-fn="move"]') as HTMLButtonElement).click());
    expect(dialog.container.querySelector('.dlg .dh b')?.textContent).toBe('Move Plant');
  });
});

describe('company creation setting row', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('is a setRow marked as an addition, and Add company leaves the Companies page while off', () => {
    model();
    const page = render(<TenantSettings />);
    const row = page.container.querySelector('.set[data-ox-new]');
    expect(row?.querySelector('b')?.textContent).toBe('Company creation');
    expect(row?.querySelector('p')?.textContent).toBe('Allow adding companies.');
    expect(row?.querySelector('.tg[data-set="companyCreation"]')?.textContent).toBe('Disable');
    const on = render(<Companies />);
    expect((on.container.querySelector('[data-act="addCompany"]')?.parentElement as HTMLElement).style.display).toBe('');
    on.unmount();
    store.ui.settings = { ...settings, companyCreation: false };
    const off = render(<Companies />);
    expect((off.container.querySelector('[data-act="addCompany"]')?.parentElement as HTMLElement).style.display).toBe('none');
  });

  it('newDomainDialog focuses the name when it is empty and sends nothing', async () => {
    model();
    const create = vi.spyOn(api, 'proposeCreateDomain').mockResolvedValue(change('create_domain'));
    const dialog = render(<Dialog />);
    act(() => newDomainDialog());
    act(() => (dialog.container.querySelectorAll('.dlg .df .btn')[1] as HTMLButtonElement).click());
    await flush();
    expect(create).not.toHaveBeenCalled();
    expect(store.ui.dialogs).toHaveLength(1);
    store.ui.dialogs = [];
  });
});
