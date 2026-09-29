import { api } from '../api/client';
import { ApiError, type DocumentExtraction, type ImportResult } from '../api/types';
import { store } from '../store/store';
import { POLL_MS, readWholeDocument } from './wholeDocument';

const imported: ImportResult = {
  importId: 'imp-1',
  expiresAt: '2026-09-29T13:00:00Z',
  fileName: 'handbook.docx',
  origin: 'document',
  originDetail: { fileName: 'handbook.docx', mediaType: 'text/plain' },
  sentences: ['The plant runs production lines.'],
};

const job = (over: Partial<DocumentExtraction>): DocumentExtraction => ({
  id: 'job-1',
  importId: 'imp-1',
  companyId: 'co-1',
  state: 'queued',
  phase: null,
  chunks: 3,
  outlineChunksDone: 0,
  sectionChunksDone: 0,
  outlineNodes: 0,
  tokensUsed: 0,
  tokenCeiling: 1_000_000,
  nodeCeiling: 2000,
  draftCount: 0,
  degraded: false,
  failureReason: null,
  cancelRequested: false,
  createdAt: '2026-09-29T12:00:00Z',
  startedAt: null,
  finishedAt: null,
  expiresAt: null,
  submittedAt: null,
  ...over,
});

describe('whole-document reading', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('follows the job in the caption and proposes every draft of its result', async () => {
    vi.useFakeTimers();
    vi.spyOn(api, 'listProposals').mockResolvedValue({ items: [], page: 1, pageSize: 1, total: 0 });
    vi.spyOn(api, 'startDocumentExtraction').mockResolvedValue(job({ state: 'running', phase: 'sections', outlineChunksDone: 3, sectionChunksDone: 1 }));
    vi.spyOn(api, 'getDocumentExtraction').mockResolvedValue(job({ state: 'succeeded', draftCount: 2 }));
    vi.spyOn(api, 'getDocumentExtractionResult').mockResolvedValue({
      extractionId: 'job-1',
      outline: [],
      drafts: [
        { type: 'concept', companyId: 'co-1', parentId: 'root-1', label: 'Plant', domainKey: 'production', action: 'has' },
        { type: 'concept', companyId: 'co-1', parentId: '', parentLabel: 'Plant', label: 'Line', domainKey: 'production', action: 'runs' },
      ],
      notes: [],
      unresolved: [],
    });
    const propose = vi.spyOn(api, 'proposeDocumentExtraction').mockResolvedValue([{} as never, {} as never]);
    const done = readWholeDocument(imported, 'co-1');
    await vi.advanceTimersByTimeAsync(0);
    expect(store.ui.caption).toMatchObject({ kicker: 'Reading handbook.docx', text: 'Outline 3 of 3 · sections 1 of 3' });
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(await done).toBe('proposed');
    expect(propose).toHaveBeenCalledWith('job-1', [0, 1]);
    expect(store.ui.caption).toMatchObject({ kicker: 'Reading handbook.docx', text: '2 proposals from handbook.docx' });
  });

  it('reports a reading that is not available, so the import falls back to sentence by sentence', async () => {
    vi.spyOn(api, 'startDocumentExtraction').mockRejectedValue(new ApiError(403, { title: 'forbidden', status: 403, code: 'forbidden' }));
    expect(await readWholeDocument(imported, 'co-1')).toBe('unavailable');
    expect(store.ui.caption.text).toBe('Whole-document reading is not available');
  });

  it('has nothing to propose when the job found nothing grounded', async () => {
    vi.spyOn(api, 'startDocumentExtraction').mockResolvedValue(job({ state: 'failed', failureReason: 'no_drafts', finishedAt: 'x' }));
    expect(await readWholeDocument(imported, 'co-1')).toBe('nothing');
    expect(store.ui.caption.text).toBe('Nothing to propose from handbook.docx');
  });
});
