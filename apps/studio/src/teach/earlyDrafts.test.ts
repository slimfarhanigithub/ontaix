import { api } from '../api/client';
import { installMockFetch } from '../api/mock/install';
import type {
  ProposalDraft,
  Proposal,
  TeachDraftEvent,
  TeachRequest,
  TeachResult,
  TeachRetractEvent,
  TeachStreamListener,
} from '../api/types';
import { addCompany } from '../canvas/state';
import type { Company, Node } from '../canvas/types';
import { store } from '../store/store';
import { speechStream, teach } from './teach';

const base: TeachResult = {
  outcome: 'understood',
  domainKey: null,
  intents: [],
  drafts: [],
  statements: [],
  caption: 'ok',
  origin: 'text',
  originDetail: null,
  extractor: 'llm',
  degraded: false,
  llmOutcome: 'used',
  draftNotes: [],
  unresolved: [],
  segments: [{ index: 0, span: { start: 0, end: 9 } }],
};

const note = { extractor: 'llm' as const, confidence: 0.9 };
const born = (label: string, parent = 'root'): ProposalDraft =>
  ({ type: 'concept', companyId: 'insight', parentId: parent, label, domainKey: 'sales', action: 'sells', origin: 'text' }) as ProposalDraft;
const draftLine = (index: number, draft: ProposalDraft): TeachDraftEvent => ({ type: 'draft', index, draft, note });
const retractLine = (...indexes: number[]): TeachRetractEvent => ({ type: 'retract', indexes });

/** The proposal the API makes of a concept draft, with the ids its artefacts get. */
function proposalOf(draft: ProposalDraft, id: string): Proposal {
  const d = draft as ProposalDraft & { label: string; parentId: string; seed?: number };
  return {
    type: 'concept',
    artefacts: {
      concepts: [{ id, companyId: 'insight', label: d.label, parentId: d.parentId, domainKey: 'sales' }],
      relations: [{ id: `${id}-birth`, kind: 'rel', label: 'sells', aId: d.parentId, bId: id, seed: d.seed ?? 0.5, rest: 230 }],
    },
  } as unknown as Proposal;
}

const cells = (label: string): Node[] => store.s.nodes.filter((n) => n.label === label);

describe('cells of streamed drafts', () => {
  let before: typeof store.s.activeCompany;
  let counts: number[];
  let insight: Company;

  beforeEach(() => {
    const s = store.s;
    before = s.activeCompany;
    counts = [s.companies.length, s.nodes.length, s.links.length];
    insight = addCompany(s, 'Insight', '');
    insight.sid = 'insight';
    insight.root!.sid = 'root';
    s.activeCompany = insight;
  });
  afterEach(() => {
    const s = store.s;
    s.links.splice(counts[2]);
    s.nodes.splice(counts[1]);
    s.companies.splice(counts[0]);
    s.activeCompany = before;
    vi.restoreAllMocks();
  });

  /** Proposals the batch endpoint makes, replayed as their events are, before it answers. */
  function batches() {
    const sent: ProposalDraft[][] = [];
    vi.spyOn(api, 'createProposalBatch').mockImplementation(async (drafts) => {
      sent.push(drafts);
      const made = drafts.map((d, i) => proposalOf(d, `c${sent.length}-${i}`));
      for (const p of made) store.applyCreated(p);
      return made;
    });
    return sent;
  }

  it('divides a streamed concept off its parent at once, and its proposal takes the cell over', async () => {
    const sent = batches();
    let seenWhileParsing: Node[] = [];
    vi.spyOn(api, 'teachParse').mockImplementation(async (_body, listen) => {
      listen?.(draftLine(0, born('Services')));
      seenWhileParsing = cells('Services');
      return { ...base, drafts: [born('Services')] };
    });

    expect(await teach('Insight sells services')).toBe(true);

    expect(seenWhileParsing).toHaveLength(1);
    expect(seenWhileParsing[0].pending).toBe(true);
    const [services] = cells('Services');
    expect(cells('Services')).toHaveLength(1);
    expect(services).toBe(seenWhileParsing[0]);
    expect(services.sid).toBe('c1-0');
    expect(services.dying).toBeFalsy();
    expect(services.birthLink?.sid).toBe('c1-0-birth');
    // The batch carries the link bend drawn when the draft arrived.
    const seed = (sent[0][0] as ProposalDraft & { seed: number }).seed;
    expect(services.birthLink?.seed).toBe(seed);
  });

  it('fades a retracted cell and proposes nothing for it', async () => {
    const sent = batches();
    vi.spyOn(api, 'teachParse').mockImplementation(async (_body, listen) => {
      listen?.(draftLine(0, born('Services')));
      listen?.(retractLine(0));
      return { ...base, outcome: 'not_understood', llmOutcome: 'invalid_output', drafts: [] };
    });

    expect(await teach('Insight sells services')).toBe(false);

    const [services] = cells('Services');
    expect(services.dying).toBeTruthy();
    expect(services.sid).toBeNull();
    expect(sent).toEqual([]);
  });

  it('reconciles with the final result: a cell it does not hold fades, and its own drafts are born', async () => {
    batches();
    vi.spyOn(api, 'teachParse').mockImplementation(async (_body, listen) => {
      listen?.(draftLine(0, born('Services')));
      listen?.(draftLine(1, born('Offerings')));
      return { ...base, drafts: [born('Services'), born('Products')] };
    });

    await teach('Insight sells services and products');

    expect(cells('Services')[0].sid).toBe('c1-0');
    expect(cells('Offerings')[0].dying).toBeTruthy();
    expect(cells('Products')).toHaveLength(1);
    expect(cells('Products')[0].sid).toBe('c1-1');
  });

  it('fades the early cells when the batch is refused', async () => {
    vi.spyOn(api, 'createProposalBatch').mockRejectedValue(new Error('offline'));
    vi.spyOn(store, 'refused').mockImplementation(() => undefined);
    vi.spyOn(api, 'teachParse').mockImplementation(async (_body, listen) => {
      listen?.(draftLine(0, born('Services')));
      return { ...base, drafts: [born('Services')] };
    });

    await teach('Insight sells services');

    expect(cells('Services')[0].dying).toBeTruthy();
  });

  it('keeps spoken sentences in order: the next is sent, and its cells drawn, once the previous is proposed', async () => {
    const order: string[] = [];
    let batch = 0;
    vi.spyOn(api, 'createProposalBatch').mockImplementation(async (drafts) => {
      order.push(`propose ${(drafts[0] as ProposalDraft & { label: string }).label}`);
      const made = drafts.map((d, i) => proposalOf(d, `${++batch}-${i}`));
      for (const p of made) store.applyCreated(p);
      return made;
    });
    const held: { body: TeachRequest; listen?: TeachStreamListener; answer: (r: TeachResult) => void }[] = [];
    vi.spyOn(api, 'teachParse').mockImplementation(
      (body, listen) => new Promise<TeachResult>((answer) => held.push({ body, listen, answer })),
    );
    const tick = () => new Promise((r) => setTimeout(r, 0));
    const stream = speechStream();

    stream.sentence('Insight sells services.');
    stream.sentence('Insight sells products.');
    await tick();
    expect(held.map((h) => h.body.text)).toEqual(['Insight sells services.']);
    held[0].listen?.(draftLine(0, born('Services')));
    order.push('drawn Services');
    held[0].answer({ ...base, origin: 'speech', drafts: [born('Services')] });
    await tick();
    expect(held.map((h) => h.body.text)).toEqual(['Insight sells services.', 'Insight sells products.']);
    held[1].listen?.(draftLine(0, born('Products')));
    order.push('drawn Products');
    held[1].answer({ ...base, origin: 'speech', drafts: [born('Products')] });
    await stream.settled();

    expect(order).toEqual(['drawn Services', 'propose Services', 'drawn Products', 'propose Products']);
    expect(held.every((h) => h.body.origin === 'speech' && typeof h.listen === 'function')).toBe(true);
    expect(cells('Services')[0].sid).toBe('1-0');
    expect(cells('Products')[0].sid).toBe('2-0');
  });
});

describe('the streamed parse over the mock API', () => {
  const realFetch = window.fetch;
  afterEach(() => {
    window.fetch = realFetch;
  });

  it('sends each draft, then the result the plain parse answers', async () => {
    installMockFetch();
    const scene = await api.getScene();
    const request: TeachRequest = { companyId: scene.companies[0].id, text: 'A plant has machines', origin: 'text' };
    const lines: (TeachDraftEvent | TeachRetractEvent)[] = [];

    const streamed = await api.teachParse(request, (e) => lines.push(e));
    const plain = await api.teachParse(request);

    expect(streamed).toEqual(plain);
    expect(plain.drafts.length).toBeGreaterThan(0);
    expect(lines.map((e) => e.type === 'draft' && e.draft)).toEqual(plain.drafts);
    expect(lines.map((e) => e.type === 'draft' && e.index)).toEqual(plain.drafts.map((_, i) => i));
  });
});
