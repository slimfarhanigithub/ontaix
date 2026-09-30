import { act, fireEvent, render } from '@testing-library/react';

import { api } from '../api/client';
import { ApiError, type DocumentExtraction, type ImportDetection, type ImportResult, type OntologyImportResult } from '../api/types';
import { store } from '../store/store';
import { importAgain, importFile } from '../teach/importFile';
import { READINGS } from '../teach/importReading';
import { Dialog } from './Dialog';
import { ImportAsPill } from './ImportAs';

const flush = () => act(() => new Promise((r) => setTimeout(r, 0)));

const mapped: OntologyImportResult = {
  ontologyImportId: 'oi-1',
  expiresAt: '2026-09-30T12:00:00Z',
  companyId: 'company-a',
  parentConceptId: null,
  format: 'turtle',
  languages: ['en'],
  individuals: 'skip',
  drafts: [],
  notes: [],
  skipped: [],
};

const imported: ImportResult = {
  importId: 'i-1',
  expiresAt: '2026-09-30T12:00:00Z',
  fileName: 'plant.ttl',
  origin: 'document',
  originDetail: { fileName: 'plant.ttl', mediaType: 'text/plain' },
  sentences: [],
  skipped: 0,
};

function detected(d: ImportDetection) {
  return vi.spyOn(api, 'detectImport').mockResolvedValue(d);
}

describe('import routing and #imAs', () => {
  let before: typeof store.s.activeCompany;
  beforeEach(() => {
    before = store.s.activeCompany;
    store.s.activeCompany = { sid: 'company-a' } as typeof before;
    store.ui.lastImport = null;
    store.ui.dialogs = [];
    vi.spyOn(store, 'refreshProposals').mockResolvedValue();
    vi.spyOn(api, 'proposeOntologyImport').mockResolvedValue([]);
  });
  afterEach(() => {
    store.s.activeCompany = before;
    store.ui.lastImport = null;
    vi.restoreAllMocks();
  });

  it('shows no pill before a file is imported', () => {
    const { container } = render(<ImportAsPill hidden={false} />);
    expect(container.querySelector('#imAs')).toBeNull();
  });

  it('sends a detected ontology to ontology import in the detected format', async () => {
    detected({ kind: 'ontology', format: 'turtle', mediaType: 'text/plain' });
    const mapping = vi.spyOn(api, 'importOntology').mockResolvedValue(mapped);
    const upload = vi.spyOn(api, 'importSentences');
    const { container } = render(<ImportAsPill hidden={false} />);

    await act(() => importFile(new File(['@prefix : <x#> .'], 'notes.txt')));

    expect(mapping).toHaveBeenCalledTimes(1);
    expect(mapping.mock.calls[0][1]).toMatchObject({ companyId: 'company-a', format: 'turtle' });
    expect(upload).not.toHaveBeenCalled();
    expect(container.querySelector('#imAs')?.textContent).toBe('Read as: Ontology (Turtle)');
    expect(store.ui.importing).toBe(false);
  });

  it('reads a detected document whole, with the detected media type', async () => {
    detected({ kind: 'document', format: null, mediaType: 'application/pdf' });
    const upload = vi.spyOn(api, 'importSentences').mockResolvedValue({ ...imported, fileName: 'report.txt' });
    const whole = vi
      .spyOn(api, 'startDocumentExtraction')
      .mockResolvedValue({ id: 'x-1', state: 'failed', failureReason: 'no_drafts' } as DocumentExtraction);
    const mapping = vi.spyOn(api, 'importOntology');
    const file = new File(['%PDF-1.4'], 'report.txt');

    await importFile(file);

    expect(upload).toHaveBeenCalledWith(file, 'application/pdf');
    expect(whole).toHaveBeenCalledWith('i-1', 'company-a');
    expect(mapping).not.toHaveBeenCalled();
    expect(store.ui.lastImport?.reading).toBe('whole');
  });

  it('lists every reading and imports the same file again the way chosen', async () => {
    detected({ kind: 'ontology', format: 'turtle', mediaType: 'text/plain' });
    const mapping = vi.spyOn(api, 'importOntology').mockResolvedValue(mapped);
    const upload = vi.spyOn(api, 'importSentences').mockResolvedValue(imported);
    const file = new File(['@prefix : <x#> .'], 'plant.ttl');
    await importFile(file);
    const { container } = render(
      <>
        <ImportAsPill hidden={false} />
        <Dialog />
      </>,
    );

    fireEvent.click(container.querySelector('#imAs') as HTMLButtonElement);
    await flush();
    const select = document.querySelector('#imAsRead') as HTMLSelectElement;
    expect(document.querySelector('.dlg.sm .dh b')?.textContent).toBe('Read plant.ttl as');
    expect(Array.from(select.options, (o) => o.textContent)).toEqual(READINGS.map((r) => r.label));
    expect(Array.from(select.options, (o) => o.textContent)).toEqual([
      'Document (whole)',
      'Document (sentences)',
      'Ontology (Turtle)',
      'Ontology (RDF/XML)',
      'Ontology (JSON-LD)',
      'Ontology (OWL/XML)',
      'Ontology (N-Triples)',
      'Ontology (OBO)',
      'Ontology (CSV)',
      'Ontology (XLSX)',
    ]);
    expect(select.value).toBe('turtle');
    expect(document.querySelector('.dlg')?.textContent).toContain(
      'Detected as Ontology (Turtle). The file is imported again, read the way chosen.',
    );

    fireEvent.change(select, { target: { value: 'sentences' } });
    fireEvent.click(Array.from(document.querySelectorAll<HTMLButtonElement>('.dlg button')).find((b) => b.textContent === 'Import again')!);
    await flush();
    await flush();

    expect(upload).toHaveBeenCalledWith(file, 'text/plain');
    expect(store.ui.lastImport?.reading).toBe('sentences');
    expect(container.querySelector('#imAs')?.textContent).toBe('Read as: Document (sentences)');

    await act(() => importAgain('rdf_xml'));
    expect(mapping).toHaveBeenLastCalledWith(file, expect.objectContaining({ format: 'rdf_xml' }));
  });

  it('shows a detection refusal in the caption and keeps no file', async () => {
    vi.spyOn(api, 'detectImport').mockRejectedValue(
      new ApiError(415, { title: 'Unsupported', status: 415, code: 'unsupported_media_type', detail: 'the file is not UTF-8 text' }),
    );
    const caption = vi.spyOn(store, 'caption');

    await importFile(new File(['x'], 'run.exe'));

    expect(caption).toHaveBeenLastCalledWith('Import failed', 'run.exe could not be read (the file is not UTF-8 text).');
    expect(store.ui.lastImport).toBeNull();
    expect(store.ui.importing).toBe(false);
  });
});
