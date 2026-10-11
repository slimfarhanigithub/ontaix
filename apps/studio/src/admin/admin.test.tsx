import { act, fireEvent, render } from '@testing-library/react';

import { api } from '../api/client';
import { ApiError, type CostSummary } from '../api/types';
import { addCompany, addLink, addNode, domainOf } from '../canvas/state';
import { Dialog } from '../shell/Dialog';
import { store } from '../store/store';
import { directory } from './adminData';
import { changeSetting } from './actions';
import { AuditLog, CostManagement } from './pages/GovernancePages';
import { Companies, DomainProducts, Entities, Relationships } from './pages/ModelPages';
import { Overview, TenantSettings } from './pages/PortalPages';

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
  addLink(s, n, m, 'rel', 560, PAYLOAD);
  store.ui.settings = { ...settings };
  directory.audit = [{ id: 1, at: '2026-09-28T09:00:00Z', actor: { kind: 'user' }, kind: PAYLOAD, what: PAYLOAD, ok: true, origin: null, companyIds: [] }];
  directory.auditTotal = 1;
  directory.loaded = true;
  return { a, b, n, m };
}

const cost: CostSummary = {
  month: '2026-10-01',
  measuredEur: 0,
  allocatedEur: 0,
  agentsRegistered: 0,
  agentsWithAccess: 0,
  reads: 0,
  byPlatform: [],
  llm: {
    calls: 148,
    inputTokens: 412_300,
    outputTokens: 61_750,
    tokensUsed: 474_050,
    tokenCap: 2_000_000,
    ocrPagesUsed: 36,
    ocrPageCap: 1000,
    costEur: 1.87,
    byPurpose: [
      { purpose: 'teach_extraction', calls: 121, costEur: 0.62 },
      { purpose: 'document_ocr', calls: 4, pages: 36, costEur: 0.26 },
    ],
  },
};

describe('admin pages render user text as text', () => {
  afterEach(() => {
    store.ui.dialogs = [];
    store.ui.toasts = [];
  });

  it.each([
    ['Entities', Entities],
    ['Relationships', Relationships],
    ['Companies', Companies],
    ['Domain products', DomainProducts],
    ['Audit log', AuditLog],
  ])('%s', async (_, Page) => {
    hostileModel();
    const { container } = render(<Page />);
    await act(() => new Promise((r) => setTimeout(r, 1)));
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain(PAYLOAD);
  });
});

describe('the portal without data sources, connectors, bindings, groups, users, roles and agents', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.toasts = [];
  });

  it('Overview counts companies, concepts, relations and proposals, nothing bound and no source', () => {
    hostileModel();
    store.ui.proposals = [];
    const { container } = render(<Overview />);
    const kpis = [...container.querySelectorAll('.kpis div')].map((d) => `${d.querySelector('b')?.textContent} ${d.querySelector('span')?.textContent}`);
    expect(kpis).toEqual(['2 companies', '2 concepts · 0 pending', '1 relations', '0 proposals awaiting approval']);
    expect(container.textContent).not.toMatch(/bound|data source|agent/i);
  });

  it('Tenant settings has no row for connectors, refresh, coverage or discovered attributes', () => {
    hostileModel();
    const { container } = render(<TenantSettings />);
    const keys = [...container.querySelectorAll('.set [data-set]')].map((t) => t.getAttribute('data-set'));
    expect(keys).toEqual([
      'liveTeaching',
      'voice',
      'importDocs',
      'everyoneTeaches',
      'approvalRequired',
      'twoApprovers',
      'notifyOwners',
      'multiCompany',
      'companyCreation',
      'crossCompany',
      'animations',
      'legend',
    ]);
    expect(container.querySelector('#refreshSel')).toBeNull();
  });

  it('Cost management shows the month’s model calls, tokens and OCR pages against their caps, the estimate and the purposes', async () => {
    hostileModel();
    vi.spyOn(api, 'getCost').mockResolvedValue(cost);
    const { container } = render(<CostManagement />);
    await act(() => new Promise((r) => setTimeout(r, 1)));
    const kpis = [...container.querySelectorAll('.kpis div')].map((d) => `${d.querySelector('b')?.textContent} ${d.querySelector('span')?.textContent}`);
    expect(kpis).toEqual([
      '148 model calls this month',
      '474,050 tokens of 2,000,000 this month',
      '36 OCR pages of 1,000 this month',
      '€ 1.87 estimated · 412,300 in · 61,750 out',
    ]);
    const rows = [...container.querySelectorAll('.tbl tbody tr')].map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent));
    expect(rows).toEqual([
      ['Teach extraction', '121', '—', '€ 0.62'],
      ['Document OCR', '4', '36', '€ 0.26'],
    ]);
    expect(container.textContent).not.toMatch(/agent|registry|platform|allocated/i);
    expect(container.querySelector('.set')).toBeNull();
  });

  it('Cost management reads a cap of 0 as the step being off, and an empty month as no call', async () => {
    hostileModel();
    vi.spyOn(api, 'getCost').mockResolvedValue({ ...cost, llm: { ...cost.llm, calls: 0, tokensUsed: 0, tokenCap: 0, ocrPagesUsed: 0, ocrPageCap: 0, costEur: 0, byPurpose: [] } });
    const { container } = render(<CostManagement />);
    await act(() => new Promise((r) => setTimeout(r, 1)));
    const spans = [...container.querySelectorAll('.kpis span')].map((d) => d.textContent);
    expect(spans[1]).toBe('tokens · the model step is off');
    expect(spans[2]).toBe('OCR pages · OCR is off');
    expect(container.querySelector('.tbl tbody')?.textContent).toBe('No model call this month.');
  });

  it('an unavailable cost endpoint leaves the page at zero and shows the toast', async () => {
    hostileModel();
    vi.spyOn(api, 'getCost').mockRejectedValue(new ApiError(404, { title: 'Not Found', status: 404, code: 'not_found' }));
    const { container } = render(<CostManagement />);
    await act(() => new Promise((r) => setTimeout(r, 1)));
    expect(container.querySelector('.kpis b')?.textContent).toBe('0');
    expect(store.ui.toasts.map((t) => [t.strong, t.text])).toEqual([['Unavailable', 'Not Found']]);
  });
});

describe('Companies may interact', () => {
  afterEach(() => {
    store.ui.dialogs = [];
  });

  it('asks for the typed word before removing cross-company relationships', () => {
    hostileModel();
    const { container } = render(<Dialog />);
    act(() => {
      void changeSetting('crossCompany');
    });
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
