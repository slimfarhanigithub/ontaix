import { act, fireEvent, render } from '@testing-library/react';

import { api } from '../api/client';
import { ApiError, type Proposal } from '../api/types';
import { addCompany, addNode, domainOf } from '../canvas/state';
import { Dialog } from '../shell/Dialog';
import { store } from '../store/store';
import { removeCompanyDialog, renameDialog } from './actions';
import { toggleDomainVisible } from './pages/ModelPages';

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
  const n = addNode(s, { label: 'Plant', sub: '', kind: 'concept', company: home, domain: domainOf(s, 'production', home) });
  n.sid = 'c-1';
  return { home, other, n };
}

const toastLeads = () => store.ui.toasts.map((t) => t.strong);

describe('admin review fixes', () => {
  beforeEach(() => {
    store.ui.settings = { refresh: '15 min' } as typeof store.ui.settings;
  });
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.dialogs = [];
    store.ui.toasts = [];
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
    vi.spyOn(api, 'deletionImpact').mockResolvedValue({ concepts: 1, descendants: 0, relations: 0, crossCompanyRelations: 0, bindings: 0, attributes: 0, sources: 0, cascadedProposals: 0, names: ['Valve'] });
    vi.spyOn(api, 'proposeRemoveCompany').mockRejectedValue(refusal(403, 'forbidden'));
    const { container } = render(<Dialog />);
    await act(() => removeCompanyDialog(other));
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
