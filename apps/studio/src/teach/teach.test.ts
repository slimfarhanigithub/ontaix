import { api } from '../api/client';
import { ApiError, type ProposalDraft, type TeachRequest, type TeachResult } from '../api/types';
import { store } from '../store/store';
import { teach, teachSessionId } from './teach';

const result: TeachResult = {
  outcome: 'not_understood',
  domainKey: null,
  intents: [],
  drafts: [],
  statements: [],
  caption: 'Try again',
  origin: 'text',
  originDetail: null,
  extractor: 'rules',
  degraded: false,
  llmOutcome: 'not_triggered',
  draftNotes: [],
  unresolved: [],
  segments: [{ index: 0, span: { start: 0, end: 9 } }],
};

describe('teach sessions', () => {
  afterEach(() => vi.restoreAllMocks());

  it('keeps one session per company and starts a new one when the company changes', () => {
    const first = teachSessionId('company-a');
    expect(teachSessionId('company-a')).toBe(first);
    expect(first).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    const second = teachSessionId('company-b');
    expect(second).not.toBe(first);
    expect(teachSessionId('company-a')).not.toBe(first);
  });

  it('sends the session with every sentence taught to the active company', async () => {
    const sent: TeachRequest[] = [];
    vi.spyOn(api, 'teachParse').mockImplementation(async (body) => {
      sent.push(body);
      return result;
    });
    const before = store.s.activeCompany;
    store.s.activeCompany = { sid: 'company-a' } as typeof before;
    try {
      await teach('Insight sells services');
      await teach('these services are focused around three areas, app, data and AI');
    } finally {
      store.s.activeCompany = before;
    }

    expect(sent.map((b) => b.sessionId)).toEqual([teachSessionId('company-a'), teachSessionId('company-a')]);
  });
});

describe('submitting a parse', () => {
  const drafts = [
    { type: 'relation', aId: 'a', bId: 'b', action: 'feeds' },
    { type: 'relation', aId: 'b', bId: 'c', action: 'feeds' },
  ] as ProposalDraft[];
  let before: typeof store.s.activeCompany;

  beforeEach(() => {
    before = store.s.activeCompany;
    store.s.activeCompany = { sid: 'company-a' } as typeof before;
  });
  afterEach(() => {
    store.s.activeCompany = before;
    vi.restoreAllMocks();
  });

  it('sends every draft of a partly understood parse as one batch', async () => {
    vi.spyOn(api, 'teachParse').mockResolvedValue({ ...result, outcome: 'partly_understood', drafts });
    const batch = vi.spyOn(api, 'createProposalBatch').mockResolvedValue([]);

    await teach('Plant downtime reports');

    expect(batch).toHaveBeenCalledTimes(1);
    expect(batch.mock.calls[0][0]).toHaveLength(2);
  });

  it('retries a batch refused for the proposal budget whole, after a short Retry-After', async () => {
    vi.spyOn(api, 'teachParse').mockResolvedValue({ ...result, outcome: 'understood', drafts });
    const refused = new ApiError(429, { title: 'Rate limited', status: 429, code: 'rate_limited' }, 0);
    const batch = vi.spyOn(api, 'createProposalBatch').mockRejectedValueOnce(refused).mockResolvedValue([]);

    await teach('A plant feeds lines');

    expect(batch).toHaveBeenCalledTimes(2);
    expect(batch.mock.calls[1][0]).toHaveLength(2);
  });
});
