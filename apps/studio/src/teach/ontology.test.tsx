import { fireEvent, render } from '@testing-library/react';

import { api } from '../api/client';
import { ApiError, type OntologyImportResult, type Proposal } from '../api/types';
import { Dialog } from '../shell/Dialog';
import { importChosenFile, openImportDialog } from '../shell/ImportDialog';
import { store } from '../store/store';
import * as teachModule from './teach';
import { browserLanguages, importOntology } from './ontology';

const mapped: OntologyImportResult = {
  ontologyImportId: 'oi-1',
  expiresAt: '2026-09-30T12:00:00Z',
  companyId: 'company-a',
  parentConceptId: null,
  format: 'csv',
  languages: ['fr', 'en'],
  individuals: 'skip',
  drafts: [
    { type: 'concept', companyId: 'company-a', parentId: 'root', label: 'Operations', domainKey: 'production', action: 'includes' },
    { type: 'concept', companyId: 'company-a', parentLabel: 'Operations', label: 'Maintenance', domainKey: 'production', action: 'includes' },
  ] as OntologyImportResult['drafts'],
  notes: [
    { source: 'row 2', labelLanguage: null, depth: 1, requires: [] },
    { source: 'row 3', labelLanguage: null, depth: 2, requires: [0] },
  ],
  skipped: [{ source: 'row 4', reason: 'unknown_parent' }],
};

describe('ontology import', () => {
  let before: typeof store.s.activeCompany;

  beforeEach(() => {
    before = store.s.activeCompany;
    store.s.activeCompany = { sid: 'company-a' } as typeof before;
    vi.spyOn(store, 'refreshProposals').mockResolvedValue();
  });
  afterEach(() => {
    store.s.activeCompany = before;
    store.ui.dialogs = [];
    vi.restoreAllMocks();
  });

  it('sends the browser languages, skips individuals and proposes every draft', async () => {
    const sent: unknown[] = [];
    vi.spyOn(api, 'importOntology').mockImplementation(async (file, body) => {
      sent.push([file.name, body]);
      return mapped;
    });
    const propose = vi.spyOn(api, 'proposeOntologyImport').mockResolvedValue([{}, {}] as Proposal[]);
    const caption = vi.spyOn(store, 'caption');

    await importOntology(new File(['label,parent'], 'tree.csv'));

    expect(sent).toEqual([['tree.csv', { companyId: 'company-a', languages: browserLanguages(), individuals: 'skip' }]]);
    expect(propose).toHaveBeenCalledWith('oi-1', [0, 1]);
    expect(caption).toHaveBeenNthCalledWith(1, 'Mapping tree.csv', '');
    expect(caption).toHaveBeenLastCalledWith('Mapping tree.csv', '2 proposals from tree.csv · 1 skipped');
  });

  it('shows a refusal as the reference toast and proposes nothing', async () => {
    vi.spyOn(api, 'importOntology').mockRejectedValue(
      new ApiError(415, { title: 'Unsupported', status: 415, code: 'unsupported_media_type', detail: 'the file is not an ontology' }),
    );
    const propose = vi.spyOn(api, 'proposeOntologyImport');
    const toast = vi.spyOn(store, 'toast2');

    await importOntology(new File(['x'], 'x.owl'));

    expect(toast).toHaveBeenCalledWith('Refused', 'the file is not an ontology');
    expect(propose).not.toHaveBeenCalled();
  });

  it('keeps valid browser language tags, first preferred, at most ten', () => {
    expect(browserLanguages(['fr-CA', 'fr', 'FR', 'not a tag', 'en'])).toBe('fr-CA,fr,en');
    expect(browserLanguages([])).toBe('en');
    expect(browserLanguages(Array.from({ length: 12 }, (_, i) => `x${String.fromCharCode(97 + i)}`)).split(',')).toHaveLength(10);
  });
});

describe('the import dialog', () => {
  afterEach(() => {
    store.ui.dialogs = [];
    vi.restoreAllMocks();
  });

  it('offers sentence by sentence and ontology in #imMode, then reads the picked file that way', () => {
    vi.spyOn(store, 'refreshProposals').mockResolvedValue();
    const imports = vi.spyOn(teachModule, 'importDocument').mockResolvedValue();
    const mapping = vi.spyOn(api, 'importOntology').mockResolvedValue({ ...mapped, drafts: [], notes: [] });
    const picker = vi.fn();
    openImportDialog(picker);
    const { container, rerender } = render(<Dialog />);
    rerender(<Dialog />);

    const rows = container.querySelectorAll('#imMode .chk');
    expect([...rows].map((r) => r.querySelector('b')?.textContent)).toEqual(['Sentence by sentence', 'Ontology']);
    expect((container.querySelector('#imMode input:checked') as HTMLInputElement).value).toBe('sentence');
    fireEvent.click(container.querySelector('#imMode input[value=ontology]') as Element);
    fireEvent.click(container.querySelector('.df .btn.primary') as Element);
    expect(picker).toHaveBeenCalledTimes(1);

    const before = store.s.activeCompany;
    store.s.activeCompany = { sid: 'company-a' } as typeof before;
    try {
      importChosenFile(new File(['x'], 'tree.csv'));
      importChosenFile(new File(['x'], 'notes.txt'));
    } finally {
      store.s.activeCompany = before;
    }
    expect(mapping).toHaveBeenCalledTimes(1);
    expect(imports).toHaveBeenCalledTimes(1);
  });
});
