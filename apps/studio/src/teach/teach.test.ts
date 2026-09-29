import { api } from '../api/client';
import { ApiError, type ProposalDraft, type TeachRequest, type TeachResult } from '../api/types';
import { addCompany, addLink, addNode } from '../canvas/state';
import { store } from '../store/store';
import { SPEECH_PARSE_TIMEOUT_MS, importDocument, skippedText, speechStream, teach, teachSessionId, withoutKnown } from './teach';

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

describe('speaking to the teach bar', () => {
  let before: typeof store.s.activeCompany;

  beforeEach(() => {
    before = store.s.activeCompany;
    store.s.activeCompany = { sid: 'company-a' } as typeof before;
  });
  afterEach(() => {
    store.s.activeCompany = before;
    vi.restoreAllMocks();
  });

  /** A parse that answers when the test says so. */
  function heldParses() {
    const sent: TeachRequest[] = [];
    const answers: ((r: TeachResult) => void)[] = [];
    const refusals: ((err: unknown) => void)[] = [];
    vi.spyOn(api, 'teachParse').mockImplementation(
      (body) =>
        new Promise<TeachResult>((resolve, reject) => {
          sent.push(body);
          answers.push(resolve);
          refusals.push(reject);
        }),
    );
    return { sent, answers, refusals };
  }

  /** Lets pending promise callbacks run. */
  const tick = () => new Promise((r) => setTimeout(r, 0));
  const draft = (label: string) => ({ type: 'concept', companyId: 'company-a', parentId: 'root', label }) as ProposalDraft;

  it('sends one sentence at a time, in spoken order, as speech in the same session', async () => {
    const { sent, answers } = heldParses();
    vi.spyOn(api, 'createProposalBatch').mockResolvedValue([]);
    const stream = speechStream();

    stream.sentence('Insight sells services. ');
    stream.sentence('They are focused on data.');
    stream.sentence('It has a platform.');
    await tick();
    expect(sent.map((b) => b.text)).toEqual(['Insight sells services.']);
    answers[0](result);
    await tick();
    expect(sent.map((b) => b.text)).toEqual(['Insight sells services.', 'They are focused on data.']);
    answers[1](result);
    await tick();
    answers[2](result);
    await stream.settled();

    expect(sent.map((b) => b.text)).toEqual(['Insight sells services.', 'They are focused on data.', 'It has a platform.']);
    expect(sent.every((b) => b.origin === 'speech')).toBe(true);
    expect(new Set(sent.map((b) => b.sessionId))).toEqual(new Set([teachSessionId('company-a')]));
  });

  it('never has two sentences in flight and proposes each before the next is sent', async () => {
    let inFlight = 0;
    let most = 0;
    const order: string[] = [];
    vi.spyOn(api, 'teachParse').mockImplementation(async (body) => {
      most = Math.max(most, ++inFlight);
      order.push(`parse ${body.text}`);
      await tick();
      inFlight--;
      return { ...result, outcome: 'understood', drafts: [draft(body.text as string)] };
    });
    vi.spyOn(api, 'createProposalBatch').mockImplementation(async (drafts) => {
      order.push(`propose ${(drafts[0] as { label: string }).label}`);
      return [];
    });
    const stream = speechStream();

    stream.sentence('Services');
    stream.sentence('Data');
    await stream.settled();

    expect(most).toBe(1);
    expect(order).toEqual(['parse Services', 'propose Services', 'parse Data', 'propose Data']);
  });

  it('shows a refused sentence in its place and goes on with the next', async () => {
    const { answers, refusals } = heldParses();
    const order: string[] = [];
    vi.spyOn(store, 'refused').mockImplementation(() => void order.push('refused'));
    vi.spyOn(store, 'caption').mockImplementation((kicker) => void order.push(kicker));
    const stream = speechStream();

    stream.sentence('Insight sells services.');
    stream.sentence('They are focused on data.');
    await tick();
    refusals[0](new ApiError(422, { code: 'validation_failed', title: 'Too long', status: 422 } as ApiError['problem']));
    await tick();
    answers[1]({ ...result, outcome: 'not_understood' });
    await stream.settled();

    expect(order).toEqual(['refused', 'Not understood']);
  });

  it('keeps one request in flight across recordings started one after another', async () => {
    let inFlight = 0;
    let most = 0;
    const sent: string[] = [];
    vi.spyOn(api, 'teachParse').mockImplementation(async (body) => {
      most = Math.max(most, ++inFlight);
      sent.push(body.text as string);
      await tick();
      inFlight--;
      return result;
    });
    vi.spyOn(store, 'caption').mockImplementation(() => undefined);

    const first = speechStream();
    first.sentence('Insight sells services.');
    const second = speechStream();
    second.sentence('They are focused on data.');
    await second.settled();

    expect(most).toBe(1);
    expect(sent).toEqual(['Insight sells services.', 'They are focused on data.']);
  });

  it('gives up a parse with no answer after the timeout and moves on', async () => {
    vi.useFakeTimers();
    try {
      const sent: string[] = [];
      vi.spyOn(api, 'teachParse').mockImplementation((body) => {
        sent.push(body.text as string);
        return sent.length === 1 ? new Promise<TeachResult>(() => undefined) : Promise.resolve(result);
      });
      const toast = vi.spyOn(store, 'toast2').mockImplementation(() => undefined);
      vi.spyOn(store, 'caption').mockImplementation(() => undefined);
      const stream = speechStream();

      stream.sentence('Insight sells services.');
      stream.sentence('They are focused on data.');
      await vi.advanceTimersByTimeAsync(SPEECH_PARSE_TIMEOUT_MS - 1);
      expect(sent).toEqual(['Insight sells services.']);
      await vi.advanceTimersByTimeAsync(1);
      await stream.settled();

      expect(sent).toEqual(['Insight sells services.', 'They are focused on data.']);
      expect(toast).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows one toast for a run of 429 refusals and sends the sentences again after Retry-After', async () => {
    vi.useFakeTimers();
    try {
      const limited = () => new ApiError(429, { code: 'rate_limited', title: 'Too many requests', status: 429 } as ApiError['problem'], 2);
      const answers = [limited(), limited(), limited(), result, result];
      const sent: { text: string; at: number }[] = [];
      vi.spyOn(api, 'teachParse').mockImplementation(async (body) => {
        sent.push({ text: body.text as string, at: Date.now() });
        const next = answers.shift();
        if (next instanceof ApiError) throw next;
        return next as TeachResult;
      });
      const refused = vi.spyOn(store, 'refused').mockImplementation(() => undefined);
      vi.spyOn(store, 'caption').mockImplementation(() => undefined);
      const start = Date.now();
      const stream = speechStream();

      stream.sentence('one');
      stream.sentence('two');
      stream.sentence('three');
      await vi.runAllTimersAsync();
      await stream.settled();

      expect(refused).toHaveBeenCalledTimes(1);
      expect(sent.map((s) => s.text)).toEqual(['one', 'one', 'two', 'two', 'three']);
      expect(sent.map((s) => s.at - start)).toEqual([0, 2000, 2000, 4000, 4000]);
    } finally {
      vi.useRealTimers();
    }
  });

  it('sends nothing for a sentence with no words', () => {
    const { sent } = heldParses();
    speechStream().sentence('   ');
    expect(sent).toEqual([]);
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

describe('Ontology import mode', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends the file to ontology import, not to sentence extraction', async () => {
    const before = store.s.activeCompany;
    store.s.activeCompany = { sid: 'company-a' } as typeof before;
    vi.spyOn(store, 'refreshProposals').mockResolvedValue();
    const upload = vi.spyOn(api, 'importSentences');
    const mapping = vi.spyOn(api, 'importOntology').mockResolvedValue({
      ontologyImportId: 'oi-1',
      expiresAt: '2026-09-30T12:00:00Z',
      companyId: 'company-a',
      parentConceptId: null,
      format: 'rdf_xml',
      languages: ['en'],
      individuals: 'skip',
      drafts: [],
      notes: [],
      skipped: [],
    });
    try {
      await importDocument(new File(['a'], 'model.owl'), 'ontology');
    } finally {
      store.s.activeCompany = before;
    }
    expect(mapping).toHaveBeenCalledTimes(1);
    expect(upload).not.toHaveBeenCalled();
    expect(store.ui.importing).toBe(false);
  });
});

describe('importing a document', () => {
  afterEach(() => vi.restoreAllMocks());

  it('names the skipped short fragments only when there are some', () => {
    expect(skippedText(0)).toBe('');
    expect(skippedText(1)).toBe(' 1 short fragment skipped.');
    expect(skippedText(3)).toBe(' 3 short fragments skipped.');
  });

  it('shows the skipped fragments in the import caption', async () => {
    const before = store.s.activeCompany;
    const skip = store.s.SKIP;
    store.s.activeCompany = { sid: 'company-a' } as typeof before;
    store.s.SKIP = true;
    vi.spyOn(api, 'importSentences').mockResolvedValue({
      importId: 'i',
      expiresAt: '2026-09-29T00:00:00Z',
      fileName: 'brief.md',
      origin: 'document',
      originDetail: { fileName: 'brief.md', mediaType: 'text/markdown' },
      sentences: ['Insight sells services.'],
      skipped: 3,
    });
    vi.spyOn(api, 'teachParse').mockResolvedValue(result);
    vi.spyOn(store, 'refreshProposals').mockResolvedValue();
    const caption = vi.spyOn(store, 'caption');
    try {
      await importDocument(new File(['x'], 'brief.md'));
    } finally {
      store.s.activeCompany = before;
      store.s.SKIP = skip;
    }

    expect(caption).toHaveBeenLastCalledWith(
      'Import finished',
      'brief.md: 1 sentences read, 0 proposals waiting for approval on the right. 3 short fragments skipped.',
    );
  });
});
