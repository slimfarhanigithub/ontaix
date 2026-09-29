import { act, fireEvent, render } from '@testing-library/react';

import { addCompany, addLink, addNode, addSource, domainOf } from '../canvas/state';
import { Dialog } from '../shell/Dialog';
import { store } from '../store/store';
import { directory } from './adminData';
import { changeSetting } from './actions';
import { Connectors, DataSources } from './pages/DataPages';
import { AuditLog, Groups, Users } from './pages/GovernancePages';
import { Bindings, Companies, DomainProducts, Entities, Relationships } from './pages/ModelPages';

const PAYLOAD = '<img src=x onerror=alert(1)>';

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
  crossCompany: true,
  animations: true,
  coverageDefault: false,
  legend: true,
  readOnlyConnectors: true as const,
  refresh: '15 min' as const,
  agentAccess: true,
  costCap: true,
  llmMonthlyTokenCap: 2_000_000,
};

function hostileModel() {
  const s = store.s;
  s.nodes.length = 0;
  s.links.length = 0;
  s.companies.length = 0;
  s.DOMAINS = [];
  const a = addCompany(s, PAYLOAD, PAYLOAD);
  const b = addCompany(s, `${PAYLOAD} two`, '');
  const n = addNode(s, { label: PAYLOAD, sub: '', kind: 'concept', company: a, domain: domainOf(s, 'production', a) });
  const m = addNode(s, { label: `${PAYLOAD} b`, sub: '', kind: 'concept', company: b, domain: domainOf(s, 'sales', b) });
  const src = addSource(s, a, PAYLOAD, PAYLOAD);
  n.bound = { source: src, records: 1200, fresh: PAYLOAD };
  addLink(s, n, m, 'rel', 560, PAYLOAD);
  store.ui.settings = { ...settings };
  store.ui.connectors = [{ code: PAYLOAD, name: PAYLOAD, category: PAYLOAD, scopeText: PAYLOAD }];
  directory.groups = [
    {
      id: 'g1',
      name: PAYLOAD,
      description: PAYLOAD,
      memberCount: 1,
      roles: [{ id: 'r1', role: 'owner', scope: { kind: 'company', companyId: null, label: PAYLOAD } }],
    },
  ];
  directory.users = [
    {
      id: 'u1',
      name: PAYLOAD,
      email: PAYLOAD,
      department: PAYLOAD,
      companyName: PAYLOAD,
      groups: [{ id: 'g1', name: PAYLOAD }],
      effectiveRoles: [],
    },
  ];
  directory.audit = [{ id: 1, at: '2026-09-28T09:00:00Z', actor: { kind: 'user' }, kind: PAYLOAD, what: PAYLOAD, ok: true, origin: null, companyIds: [] }];
  directory.auditTotal = 1;
  directory.loaded = true;
  return { a, b, n, m, src };
}

describe('admin pages render user text as text', () => {
  afterEach(() => {
    store.ui.dialogs = [];
    store.ui.toasts = [];
  });

  it.each([
    ['Entities', Entities],
    ['Relationships', Relationships],
    ['Bindings', Bindings],
    ['Companies', Companies],
    ['Domain products', DomainProducts],
    ['Data sources', DataSources],
    ['Connectors', Connectors],
    ['Groups', Groups],
    ['Users', Users],
    ['Audit log', AuditLog],
  ])('%s', async (_, Page) => {
    hostileModel();
    const { container } = render(<Page />);
    await act(() => new Promise((r) => setTimeout(r, 1)));
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain(PAYLOAD);
  });
});

describe('Companies may interact', () => {
  afterEach(() => {
    store.ui.dialogs = [];
  });

  it('asks for the typed word before removing cross-company relationships', () => {
    hostileModel();
    const { container } = render(<Dialog />);
    act(() => changeSetting('crossCompany'));
    const dlg = container.querySelector('.dlg');
    expect(dlg?.querySelector('.dh b')?.textContent).toBe('Disable interaction between companies?');
    expect(dlg?.querySelector('img')).toBeNull();
    expect(dlg?.querySelector('.discover')?.textContent).toBe(`${PAYLOAD} ${PAYLOAD} ${PAYLOAD} b`);
    const button = dlg?.querySelectorAll<HTMLButtonElement>('.df .btn')[1];
    const input = container.querySelector<HTMLInputElement>('#ccConfirm') as HTMLInputElement;
    expect(button?.textContent).toBe('Disable and remove relationships');
    expect(button?.disabled).toBe(true);
    expect(button?.style.opacity).toBe('0.5');
    fireEvent.change(input, { target: { value: 'disabl' } });
    expect(button?.disabled).toBe(true);
    fireEvent.change(input, { target: { value: ' Disable ' } });
    expect(button?.disabled).toBe(false);
    expect(button?.style.opacity).toBe('1');
  });
});
