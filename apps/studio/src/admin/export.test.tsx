import { act, fireEvent, render } from '@testing-library/react';

import { api, attachmentName } from '../api/client';
import { ApiError } from '../api/types';
import { addCompany, addNode, domainOf } from '../canvas/state';
import type { Domain } from '../canvas/types';
import { Dialog } from '../shell/Dialog';
import { store } from '../store/store';
import { EXPORT_FORMATS, EXPORT_SCOPES, exportRequest } from './ExportDialog';
import { Companies } from './pages/ModelPages';

function model() {
  const s = store.s;
  s.nodes.length = 0;
  s.links.length = 0;
  s.companies.length = 0;
  s.DOMAINS = [];
  const home = addCompany(s, 'Northwind Industries', '');
  const other = addCompany(s, 'Aurora Valves', '');
  home.sid = 'company-home';
  other.sid = 'company-other';
  const production = domainOf(s, 'production', home) as Domain;
  production.sid = 'dp-production';
  (domainOf(s, 'sales', home) as Domain).sid = 'dp-sales';
  addNode(s, { label: 'Plant', sub: '', kind: 'concept', company: home, domain: production });
  s.activeCompany = home;
  return { home, other };
}

async function settle() {
  await act(() => new Promise((r) => setTimeout(r, 5)));
}

describe('Export in the admin portal', () => {
  afterEach(() => {
    store.ui.dialogs = [];
    store.ui.toasts = [];
    vi.restoreAllMocks();
  });

  it('adds an Export button marked as an owner addition after Add a company', () => {
    model();
    const { container } = render(<Companies />);
    const buttons = Array.from(container.querySelectorAll<HTMLButtonElement>('.btn'));
    const exportButton = container.querySelector<HTMLButtonElement>('[data-act="export"]');
    expect(exportButton?.textContent).toBe('Export');
    expect(exportButton?.hasAttribute('data-ox-new')).toBe(true);
    expect(buttons.indexOf(exportButton as HTMLButtonElement)).toBe(buttons.length - 1);
    expect(buttons[buttons.length - 2].textContent).toBe('+ Add a company');
  });

  it('opens a dialog with the formats and scopes, and a domain choice for the domain scope', async () => {
    model();
    const page = render(<Companies />);
    const dialogs = render(<Dialog />);
    act(() => {
      fireEvent.click(page.container.querySelector('[data-act="export"]') as HTMLElement);
    });
    const dlg = dialogs.container.querySelector('.dlg') as HTMLElement;
    expect(dlg.querySelector('.dh b')?.textContent).toBe('Export the ontology');
    expect(dlg.querySelector('.dh span')?.textContent).toBe('the approved model as OWL, SKOS or a Word document');
    const format = dlg.querySelector<HTMLSelectElement>('#exFormat') as HTMLSelectElement;
    expect(Array.from(format.options).map((o) => o.textContent)).toEqual(EXPORT_FORMATS.map(([, label]) => label));
    expect(format.value).toBe('owl');
    const scope = dlg.querySelector<HTMLSelectElement>('#exScope') as HTMLSelectElement;
    expect(Array.from(scope.options).map((o) => o.textContent)).toEqual(EXPORT_SCOPES.map(([, label]) => label));
    expect(dlg.querySelector('#exCompany')).toBeNull();
    expect(Array.from(dlg.querySelectorAll('.df .btn')).map((b) => b.textContent)).toEqual(['Export']);

    fireEvent.change(scope, { target: { value: 'domain' } });
    const company = dlg.querySelector<HTMLSelectElement>('#exCompany') as HTMLSelectElement;
    expect(company.value).toBe('company-home');
    const domain = dlg.querySelector<HTMLSelectElement>('#exDomain') as HTMLSelectElement;
    expect(Array.from(domain.options).map((o) => o.value)).toEqual(['dp-production']);
    expect(exportRequest(dlg)).toEqual({ scope: 'domain', domainProductId: 'dp-production', format: 'owl' });

    fireEvent.change(company, { target: { value: 'company-other' } });
    expect(dlg.querySelectorAll('#exDomain option')).toHaveLength(0);
    expect(exportRequest(dlg)).toBeNull();
  });

  it('downloads the file the API writes and names it in a toast', async () => {
    model();
    const exported = vi
      .spyOn(api, 'exportOntology')
      .mockResolvedValue({ blob: new Blob(['@prefix ox: <https://ontaix.dev/ns#> .']), fileName: 'ontaix-northwind-industries-2026-09-30.ttl' });
    const createUrl = vi.fn(() => 'blob:export');
    Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const page = render(<Companies />);
    const dialogs = render(<Dialog />);
    act(() => {
      fireEvent.click(page.container.querySelector('[data-act="export"]') as HTMLElement);
    });
    const dlg = dialogs.container.querySelector('.dlg') as HTMLElement;
    fireEvent.change(dlg.querySelector('#exFormat') as HTMLElement, { target: { value: 'turtle' } });
    fireEvent.change(dlg.querySelector('#exScope') as HTMLElement, { target: { value: 'company' } });
    act(() => {
      fireEvent.click(dlg.querySelector('.df .btn') as HTMLElement);
    });
    await settle();

    expect(exported).toHaveBeenCalledWith({ scope: 'company', companyId: 'company-home', format: 'turtle' });
    expect(createUrl).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(store.ui.toasts.map((t) => `${t.strong} ${t.text}`)).toContain('Exported ontaix-northwind-industries-2026-09-30.ttl');
    expect(dialogs.container.querySelector('.dlg')).toBeNull();
  });

  it('keeps the dialog open and shows the refusal when the API refuses', async () => {
    model();
    vi.spyOn(api, 'exportOntology').mockRejectedValue(
      new ApiError(429, { title: 'Rate limited', status: 429, code: 'rate_limited', detail: 'the export budget of 20 units per hour is spent' }),
    );
    const page = render(<Companies />);
    const dialogs = render(<Dialog />);
    act(() => {
      fireEvent.click(page.container.querySelector('[data-act="export"]') as HTMLElement);
    });
    act(() => {
      fireEvent.click(dialogs.container.querySelector('.df .btn') as HTMLElement);
    });
    await settle();

    expect(dialogs.container.querySelector('.dlg')).not.toBeNull();
    expect(store.ui.toasts.map((t) => t.text)).toContain('the export budget of 20 units per hour is spent');
  });

  it('reads the file name of the attachment header', () => {
    expect(attachmentName('attachment; filename="ontaix-all-2026-09-30.owl"')).toBe('ontaix-all-2026-09-30.owl');
    expect(attachmentName(null)).toBeNull();
  });
});
