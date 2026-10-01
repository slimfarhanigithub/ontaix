import { act, fireEvent, render } from '@testing-library/react';

import { api } from '../api/client';
import type { DeletionImpact, Proposal } from '../api/types';
import { DOMAIN_TEMPLATES } from '../canvas/constants';
import { addCompany, addNode, domainOf } from '../canvas/state';
import type { Company, Node } from '../canvas/types';
import { store } from '../store/store';
import { Dialog } from './Dialog';
import { Drawer } from './Drawer';
import { Panel } from './Panel';
import { editableFields } from './PendingEdit';
import { SelectionBar } from './SelectionBar';
import { Tools } from './Tools';

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

function model(): { c: Company; plant: Node; line: Node } {
  const s = store.s;
  s.nodes.length = 0;
  s.links.length = 0;
  s.companies.length = 0;
  s.DOMAINS = [];
  s.selected.clear();
  store.ui.domains = DOMAIN_TEMPLATES.map((t, position) => ({ key: t.key, name: t.name, owner: t.owner, color: t.color, defaultColor: t.color, template: true, position, revision: 0 }));
  store.ui.settings = { ...settings };
  const c = addCompany(s, 'Northwind Industries', '');
  c.sid = 'co-1';
  const plant = addNode(s, { label: 'Plant', kind: 'concept', company: c, domain: domainOf(s, 'production', c), parent: c.root ?? undefined, sid: 'c-plant' });
  const line = addNode(s, { label: 'Line', kind: 'concept', company: c, domain: domainOf(s, 'production', c), parent: plant, sid: 'c-line' });
  return { c, plant, line };
}

const proposal = (extra: Partial<Proposal> = {}): Proposal =>
  ({
    id: 'p1',
    type: 'concept',
    state: 'pending',
    title: 'Plant',
    color: '#3fb8a9',
    deps: [],
    ready: true,
    html: '<b>Plant</b> <em>· Northwind Industries <b>operates</b> Plant</em>',
    relationIds: [],
    bindingIds: [],
    proposer: { kind: 'user' },
    origin: 'text',
    originDetail: null,
    approvals: [],
    createdAt: '2026-09-30T09:00:00Z',
    revision: 1,
    artefacts: { relations: [{ id: 'r1', label: 'operates' } as never] },
    ...extra,
  }) as Proposal;

const impact: DeletionImpact = { concepts: 2, descendants: 0, relations: 1, crossCompanyRelations: 0, bindings: 0, attributes: 0, sources: 0, cascadedProposals: 0, names: ['Plant', 'Line'] };

describe('inline edit of a pending draft in the panel', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.proposals = [];
    store.ui.toasts = [];
  });

  it('offers Edit on pending concept, specialisation and relation drafts only', () => {
    expect(editableFields(proposal())).toEqual({ label: true, action: true });
    expect(editableFields(proposal({ type: 'spec' }))).toEqual({ label: true, action: false });
    expect(editableFields(proposal({ type: 'relation' }))).toEqual({ label: false, action: true });
    expect(editableFields(proposal({ type: 'change' }))).toBeNull();
    expect(editableFields(proposal({ state: 'half_approved' }))).toBeNull();
    store.ui.proposals = [proposal(), proposal({ id: 'p2', type: 'change', changeKind: 'rename', title: 'Rename' })];
    const { container } = render(<Panel />);
    const edits = container.querySelectorAll('.prop .act button.edit');
    expect(edits).toHaveLength(1);
    expect(edits[0].getAttribute('data-ox-new')).toBe('');
    expect(edits[0].textContent).toBe('Edit');
  });

  it('saves the changed fields at the revision the editor opened, and the item updates in place without approval', async () => {
    store.ui.proposals = [proposal()];
    const edit = vi.spyOn(api, 'editProposal').mockResolvedValue(proposal({ revision: 2, title: 'Site', html: '<b>Site</b>' }));
    const approve = vi.spyOn(api, 'approve').mockResolvedValue({} as never);
    const { container } = render(<Panel />);
    act(() => container.querySelector<HTMLButtonElement>('.prop .act button.edit')?.click());
    const label = container.querySelector<HTMLInputElement>('.prop .form input[aria-label="Label"]');
    const action = container.querySelector<HTMLInputElement>('.prop .form input[aria-label="Action"]');
    expect(label?.value).toBe('Plant');
    expect(action?.value).toBe('operates');
    expect(container.querySelector('.prop .what')).toBeNull();
    fireEvent.change(label as HTMLInputElement, { target: { value: 'Site' } });
    fireEvent.keyDown(label as HTMLInputElement, { key: 'Enter' });
    await flush();
    expect(edit).toHaveBeenCalledWith('p1', { revision: 1, label: 'Site' });
    expect(approve).not.toHaveBeenCalled();
    expect(container.querySelector('.prop .what')?.textContent).toBe('Site');
    expect(container.querySelector('.prop .form')).toBeNull();
    // The next approval sends the new revision.
    act(() => container.querySelector<HTMLButtonElement>('.prop .act button.ok')?.click());
    await flush();
    expect(approve).toHaveBeenCalledWith('p1', 2);
  });

  it('Escape cancels, and a save refused with 409 proposal_changed keeps the panel on the newer text', async () => {
    store.ui.proposals = [proposal()];
    vi.spyOn(api, 'editProposal').mockRejectedValue(
      Object.assign(new (await import('../api/types')).ApiError(409, { title: 'changed', status: 409, code: 'proposal_changed', detail: 'Plant was edited since you read it' }), {}),
    );
    vi.spyOn(api, 'listProposals').mockResolvedValue({ items: [proposal({ revision: 2, title: 'Works', html: '<b>Works</b>' })], page: 1, pageSize: 1, total: 1 });
    const { container } = render(<Panel />);
    act(() => container.querySelector<HTMLButtonElement>('.prop .act button.edit')?.click());
    fireEvent.keyDown(container.querySelector('.prop .form input') as HTMLInputElement, { key: 'Escape' });
    expect(container.querySelector('.prop .form')).toBeNull();
    act(() => container.querySelector<HTMLButtonElement>('.prop .act button.edit')?.click());
    const label = container.querySelector('.prop .form input') as HTMLInputElement;
    fireEvent.change(label, { target: { value: 'Site' } });
    act(() => container.querySelector<HTMLButtonElement>('.prop .act button.ok')?.click());
    await flush();
    await flush();
    expect(store.ui.toasts.map((t) => [t.strong, t.text])).toEqual([['Refused', 'Plant was edited since you read it']]);
    expect(container.querySelector('.prop .what')?.textContent).toBe('Works');
  });
});

describe('drawer rename and move', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.dialogs = [];
    store.ui.drawerNode = null;
    store.ui.toasts = [];
  });

  it('offers Rename and Move to domain in the More actions menu for approved concepts only', () => {
    const { c, plant } = model();
    store.ui.drawerNode = plant;
    const shown = render(<Drawer />);
    const ids = Array.from(shown.container.querySelectorAll('.drawer .actions button')).map((b) => b.id);
    expect(ids).toEqual(['drMore']);
    expect(shown.container.querySelector('#drMore')?.getAttribute('data-ox-new')).toBe('');
    act(() => shown.container.querySelector<HTMLButtonElement>('#drMore')?.click());
    expect(document.getElementById('drRename')?.getAttribute('role')).toBe('menuitem');
    expect(document.getElementById('drMove')?.textContent).toBe('Move to domain…');
    shown.unmount();
    store.ui.drawerNode = c.root;
    const root = render(<Drawer />);
    act(() => root.container.querySelector<HTMLButtonElement>('#drMore')?.click());
    expect(document.getElementById('drRename')).toBeNull();
    expect(document.getElementById('drMove')).toBeNull();
    root.unmount();
  });

  it('Rename opens the rename proposal dialog; Move offers the other domains and proposes the move', async () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    const dialog = render(<Dialog />);
    const drawer = render(<Drawer />);
    const more = () => act(() => drawer.container.querySelector<HTMLButtonElement>('#drMore')?.click());
    more();
    act(() => document.getElementById('drRename')?.click());
    expect(dialog.container.querySelector('.dlg .dh b')?.textContent).toBe('Rename Plant');
    act(() => store.closeDialog());
    more();
    act(() => document.getElementById('drMove')?.click());
    const dlg = dialog.container.querySelector('.dlg');
    expect(dlg?.querySelector('.dh b')?.textContent).toBe('Move Plant');
    expect(dlg?.querySelector('.dh span')?.textContent).toBe('from Production to another domain product');
    const options = Array.from(dlg?.querySelectorAll('#mvDomain option') ?? []).map((o) => o.textContent);
    expect(options).toEqual(DOMAIN_TEMPLATES.filter((t) => t.key !== 'production').map((t) => t.name));
    const move = vi.spyOn(api, 'proposeMoveConcept').mockResolvedValue(proposal({ type: 'change', changeKind: 'move_concept_domain' }));
    (dlg?.querySelector('#mvDomain') as HTMLSelectElement).value = 'sales';
    act(() => (dlg?.querySelectorAll('.df .btn')[1] as HTMLButtonElement).click());
    await flush();
    expect(move).toHaveBeenCalledWith('c-plant', 'sales');
    expect(store.ui.toasts.map((t) => [t.strong, t.text])).toEqual([['Proposed', 'move of Plant to Sales']]);
    expect(store.ui.dialogs).toHaveLength(0);
  });
});

describe('selection bar', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.dialogs = [];
    store.ui.toasts = [];
    store.s.selected.clear();
  });

  it('appears with the count, proposes a bulk deletion of the selected cells through the impact dialog, and clears', async () => {
    const { plant, line } = model();
    const bar = render(<SelectionBar />);
    expect(bar.container.querySelector('#selBar')).toBeNull();
    act(() => {
      store.toggleSelected(plant);
      store.toggleSelected(line);
    });
    expect(bar.container.querySelector('#selBar')?.getAttribute('data-ox-new')).toBe('');
    expect(bar.container.querySelector('#selDelete')?.textContent).toBe('Delete selected (2)');
    const read = vi.spyOn(api, 'deletionImpact').mockResolvedValue(impact);
    const bulk = vi.spyOn(api, 'proposeBulkDelete').mockResolvedValue(proposal({ type: 'change', changeKind: 'delete_bulk' }));
    const dialog = render(<Dialog />);
    act(() => bar.container.querySelector<HTMLButtonElement>('#selDelete')?.click());
    await flush();
    expect(read).toHaveBeenCalledWith({ companyId: 'co-1', conceptIds: ['c-plant', 'c-line'], domainProductIds: [] });
    const dlg = dialog.container.querySelector('.dlg');
    expect(dlg?.querySelector('.dh b')?.textContent).toBe('Delete 2 concepts?');
    expect(dlg?.querySelector('.db')?.textContent).toBe(
      'Its 2 concepts (Plant, Line), 0 descendants, 1 relation, 0 bindings and 0 attributes go with it. This proposes a change for approval.',
    );
    const button = dlg?.querySelector('.df .btn.danger') as HTMLButtonElement;
    expect(button.textContent).toBe('Propose deletion');
    act(() => button.click());
    await flush();
    expect(bulk).toHaveBeenCalledWith({ companyId: 'co-1', conceptIds: ['c-plant', 'c-line'], domainProductIds: [] });
    expect(store.s.selected.size).toBe(0);
    expect(store.ui.toasts.map((t) => t.text)).toEqual(['deletion of 2 concepts · approve it on the canvas']);
    act(() => store.toggleSelected(plant));
    act(() => bar.container.querySelector<HTMLButtonElement>('#selClear')?.click());
    expect(bar.container.querySelector('#selBar')).toBeNull();
  });

  it('explains a selection across companies instead of sending it', async () => {
    const { plant } = model();
    const b = addCompany(store.s, 'Aurora Valves', '');
    b.sid = 'co-2';
    const valve = addNode(store.s, { label: 'Valve', kind: 'concept', company: b, sid: 'c-valve' });
    const read = vi.spyOn(api, 'deletionImpact').mockResolvedValue(impact);
    const bar = render(<SelectionBar />);
    act(() => {
      store.toggleSelected(plant);
      store.toggleSelected(valve);
    });
    act(() => bar.container.querySelector<HTMLButtonElement>('#selDelete')?.click());
    await flush();
    expect(read).not.toHaveBeenCalled();
    expect(store.ui.toasts.map((t) => [t.strong, t.text])).toEqual([['One company at a time', 'a bulk deletion covers the cells of one company']]);
  });
});

describe('company creation setting', () => {
  it('hides Add company while companyCreation is off', () => {
    model();
    store.ui.settings = { ...settings, companyCreation: false };
    const off = render(<Tools />);
    expect((off.container.querySelector('#addCo') as HTMLElement).style.display).toBe('none');
    off.unmount();
    store.ui.settings = { ...settings, companyCreation: true };
    const on = render(<Tools />);
    expect((on.container.querySelector('#addCo') as HTMLElement).style.display).toBe('');
  });
});
