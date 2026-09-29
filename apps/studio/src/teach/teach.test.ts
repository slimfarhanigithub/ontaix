import { api } from '../api/client';
import { ApiError, type ProposalDraft, type TeachRequest, type TeachResult } from '../api/types';
import { addCompany, addLink, addNode } from '../canvas/state';
import { store } from '../store/store';
import { teach, teachSessionId, withoutKnown } from './teach';

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

  it('drops the drafts the canvas already holds when a batch is refused as a duplicate, and sends the rest once', async () => {
    const s = store.s;
    const counts = [s.companies.length, s.nodes.length, s.links.length];
    const insight = addCompany(s, 'Insight', '');
    insight.sid = 'insight';
    insight.root!.sid = 'root';
    const services = addNode(s, { sid: 'services', label: 'Services', company: insight });
    addLink(s, insight.root!, services, 'rel', 230, 'has');
    store.s.activeCompany = insight;
    const known = { type: 'relation', aId: 'root', bId: 'services', action: 'Has' } as ProposalDraft;
    const born = ['AI', 'Data', 'Apps'].map(
      (label) =>
        ({ type: 'concept', companyId: 'insight', parentId: 'services', label, domainKey: 'sales', action: 'is split into' }) as ProposalDraft,
    );
    vi.spyOn(api, 'teachParse').mockResolvedValue({ ...result, outcome: 'understood', drafts: [known, ...born] });
    const duplicate = new ApiError(409, { title: 'Duplicate relation', status: 409, code: 'duplicate_relation' });
    const batch = vi.spyOn(api, 'createProposalBatch').mockRejectedValueOnce(duplicate).mockResolvedValue([]);
    const refused = vi.spyOn(store, 'refused');
    const toast = vi.spyOn(store, 'toast2').mockImplementation(() => undefined);
    try {
      await teach('Insight has services, they are split into AI, Data and Apps.');
    } finally {
      s.links.splice(counts[2]);
      s.nodes.splice(counts[1]);
      s.companies.splice(counts[0]);
    }

    expect(batch).toHaveBeenCalledTimes(2);
    expect(batch.mock.calls[1][0].map((d) => (d.type === 'concept' ? d.label : d.type))).toEqual(['AI', 'Data', 'Apps']);
    expect(refused).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith('Already there', 'Left out, already in the model: Insight has Services.');
  });

  it('shows a duplicate refusal when no draft can be told apart as already there', async () => {
    vi.spyOn(api, 'teachParse').mockResolvedValue({ ...result, outcome: 'understood', drafts });
    const duplicate = new ApiError(409, { title: 'Duplicate label', status: 409, code: 'duplicate_label' });
    const batch = vi.spyOn(api, 'createProposalBatch').mockRejectedValue(duplicate);
    const refused = vi.spyOn(store, 'refused').mockImplementation(() => undefined);

    await teach('A plant feeds lines');

    expect(batch).toHaveBeenCalledTimes(1);
    expect(refused).toHaveBeenCalledWith(duplicate);
  });
});

describe('leaving out what the canvas already holds', () => {
  let counts: number[];
  let before: typeof store.s.activeCompany;
  const concept = (label: string, parent: { parentId?: string; parentLabel?: string }) =>
    ({ type: 'concept', companyId: 'insight', label, domainKey: 'sales', action: 'has', ...parent }) as ProposalDraft;

  /** Insight with Services under its root and Sales under Services. */
  function scene() {
    const s = store.s;
    counts = [s.companies.length, s.nodes.length, s.links.length];
    before = s.activeCompany;
    const insight = addCompany(s, 'Insight', '');
    insight.sid = 'insight';
    insight.root!.sid = 'root';
    const services = addNode(s, { sid: 'services', label: 'Services', company: insight, parent: insight.root! });
    const sales = addNode(s, { sid: 'sales', label: 'Sales', company: insight, parent: services });
    return { insight, services, sales };
  }

  afterEach(() => {
    const s = store.s;
    s.links.splice(counts[2]);
    s.nodes.splice(counts[1]);
    s.companies.splice(counts[0]);
    s.activeCompany = before;
  });

  it('ignores cells and relations being deleted, as the API does', () => {
    const { insight, services } = scene();
    services.dying = { start: 0 };
    const link = addLink(store.s, insight.root!, services, 'rel', 230, 'has');
    link.dying = { start: 0 };
    const plan = withoutKnown([
      concept('Services', { parentId: 'root' }),
      { type: 'relation', aId: 'root', bId: 'services', action: 'has' } as ProposalDraft,
    ]);
    expect(plan.known).toEqual([]);
    expect(plan.fresh).toHaveLength(2);
  });

  it('re-points a child to the existing concept when it stands under the same parent', () => {
    scene();
    const plan = withoutKnown([concept('Services', { parentId: 'root' }), concept('AI', { parentLabel: 'Services' })]);
    expect(plan.known).toEqual(['Services']);
    expect(plan.orphaned).toEqual([]);
    expect(plan.fresh).toEqual([concept('AI', { parentId: 'services' })]);
  });

  it('leaves out and names the children of a concept that stands under another parent', () => {
    scene();
    const plan = withoutKnown([
      concept('Sales', { parentId: 'root' }),
      concept('Leads', { parentLabel: 'Sales' }),
      concept('Hot leads', { parentLabel: 'Leads' }),
      concept('AI', { parentId: 'services' }),
    ]);
    expect(plan.known).toEqual(['Sales']);
    expect(plan.orphaned).toEqual(['Leads', 'Hot leads']);
    expect(plan.fresh).toEqual([concept('AI', { parentId: 'services' })]);
  });

  it('names the left-out drafts in the toast after the resubmission', async () => {
    scene();
    const drafts = [concept('Sales', { parentId: 'root' }), concept('Leads', { parentLabel: 'Sales' }), concept('AI', { parentId: 'services' })];
    vi.spyOn(api, 'teachParse').mockResolvedValue({ ...result, outcome: 'understood', drafts });
    const duplicate = new ApiError(409, { title: 'Duplicate label', status: 409, code: 'duplicate_label' });
    const batch = vi.spyOn(api, 'createProposalBatch').mockRejectedValueOnce(duplicate).mockResolvedValue([]);
    const toast = vi.spyOn(store, 'toast2').mockImplementation(() => undefined);

    await teach('Insight has sales, sales has leads, and services has AI');

    expect(batch.mock.calls[1][0].map((d) => (d.type === 'concept' ? [d.label, d.parentId] : d.type))).toEqual([['AI', 'services']]);
    expect(toast).toHaveBeenCalledWith(
      'Already there',
      'Left out, already in the model: Sales. Also left out, as the existing concept stands under another parent: Leads.',
    );
    vi.restoreAllMocks();
  });
});
