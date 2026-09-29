import { act, fireEvent, render } from '@testing-library/react';

import { api } from '../api/client';
import { ApiError, type Proposal, type Source } from '../api/types';
import { addCompany, addNode, addSource, domainOf } from '../canvas/state';
import { Dialog } from '../shell/Dialog';
import { store } from '../store/store';
import { removeCompanyDialog, renameDialog } from './actions';
import { toggleDomainVisible } from './pages/ModelPages';
import { showSourceForm } from './SourceWizard';

const refusal = (status: number, code: string) => new ApiError(status, { title: code, status, code, detail: `${code} detail` });
const flush = () => act(() => new Promise((r) => setTimeout(r, 0)));

function model() {
  const s = store.s;
  s.nodes.length = 0;
  s.links.length = 0;
  s.companies.length = 0;
  s.DOMAINS = [];
  const home = addCompany(s, 'Northwind Industries', '');
  const other = addCompany(s, 'Aurora Valves', '');
  home.sid = 'co-1';
  other.sid = 'co-2';
  const src = addSource(s, home, 'SAP ERP', 'ERP');
  src.sid = 'src-1';
  const n = addNode(s, { label: 'Plant', sub: '', kind: 'concept', company: home, domain: domainOf(s, 'production', home) });
  n.sid = 'c-1';
  return { home, other, src, n };
}

const source: Source = {
  id: 'src-1',
  companyId: 'co-1',
  label: 'SAP ERP',
  kindText: 'ERP',
  connectorCode: 'SAP',
  host: 'sap-prod.northwind.local',
  scope: 'MARA',
  auth: 'managed_identity',
  refresh: '1 h',
  anchorIndex: 0,
  disabled: false,
  pending: false,
  x: 0,
  y: 0,
  pinned: false,
  feeds: 0,
  records: null,
  state: 'connected',
};

const toastLeads = () => store.ui.toasts.map((t) => t.strong);

describe('admin review fixes', () => {
  beforeEach(() => {
    store.ui.connectors = [{ code: 'SAP', name: 'SAP ERP (S/4HANA, ECC)', category: 'ERP', scopeText: 'OData / RFC · tables, CDS views' }];
    store.ui.settings = { refresh: '15 min' } as typeof store.ui.settings;
  });
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.dialogs = [];
    store.ui.toasts = [];
  });

  it('Configure keeps the source’s own authentication and refresh', async () => {
    const { src } = model();
    vi.spyOn(api, 'getSource').mockResolvedValue(source);
    const update = vi.spyOn(api, 'updateSource').mockResolvedValue(source);
    vi.spyOn(api, 'discover').mockResolvedValue({ connected: true, statusText: 'ok', objects: [] });
    const { container } = render(<Dialog />);
    await act(() => showSourceForm(src));
    expect(container.querySelector<HTMLSelectElement>('#wzAuth')?.value).toBe('Managed identity');
    expect(container.querySelector<HTMLSelectElement>('#wzRefresh')?.value).toBe('1 h');
    expect(container.querySelector<HTMLInputElement>('#wzHost')?.value).toBe('sap-prod.northwind.local');
    const next = () => container.querySelector<HTMLButtonElement>('.df .btn.primary') as HTMLButtonElement;
    fireEvent.click(next());
    fireEvent.click(next());
    await flush();
    expect(update).toHaveBeenCalledWith('src-1', { host: 'sap-prod.northwind.local', scope: 'MARA', auth: 'managed_identity', refresh: '1 h' });
  });

  it('Configure does not open with blanks when the source cannot be read', async () => {
    const { src } = model();
    vi.spyOn(api, 'getSource').mockRejectedValue(refusal(503, 'unavailable'));
    const update = vi.spyOn(api, 'updateSource');
    const { container } = render(<Dialog />);
    await act(() => showSourceForm(src));
    expect(container.querySelector('.dlg')).toBeNull();
    expect(store.ui.dialogs).toHaveLength(0);
    expect(toastLeads()).toEqual(['Unavailable']);
    expect(update).not.toHaveBeenCalled();
  });

  it('shows Proposed only when the server accepts the proposal', async () => {
    const { n } = model();
    const propose = vi.spyOn(store, 'propose');
    const { container } = render(<Dialog />);
    const renameTo = async (name: string) => {
      act(() => renameDialog(n));
      fireEvent.change(container.querySelector('#rnName') as HTMLInputElement, { target: { value: name } });
      fireEvent.click(container.querySelector('.df .btn.primary') as HTMLButtonElement);
      await flush();
    };
    propose.mockResolvedValueOnce(null);
    await renameTo('site');
    expect(toastLeads()).not.toContain('Proposed');
    propose.mockResolvedValueOnce({ id: 'p1' } as Proposal);
    await renameTo('works');
    expect(store.ui.toasts.find((t) => t.strong === 'Proposed')?.text).toBe('rename to Works');
  });

  it('a refused company removal shows the refusal, not Proposed', async () => {
    const { other } = model();
    vi.spyOn(api, 'proposeRemoveCompany').mockRejectedValue(refusal(403, 'forbidden'));
    const { container } = render(<Dialog />);
    act(() => removeCompanyDialog(other));
    fireEvent.click(container.querySelector('.df .btn.danger') as HTMLButtonElement);
    await flush();
    expect(toastLeads()).toEqual(['Refused']);
  });

  it('a refused domain visibility change is put back', async () => {
    const { home } = model();
    const d = home.domains[0];
    d.sid = 'dp-1';
    vi.spyOn(api, 'updateDomainProduct').mockRejectedValue(refusal(503, 'unavailable'));
    toggleDomainVisible(d);
    expect(d.hidden).toBe(true);
    await flush();
    expect(d.hidden).toBe(false);
    expect(toastLeads()).toEqual(['Refused']);
  });
});
