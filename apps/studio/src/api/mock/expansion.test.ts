import { createEventBus, type Envelope } from '../events';
import type {
  BranchResult,
  DocumentExtraction,
  DocumentExtractionResult,
  ExpansionResult,
  ImportResult,
  Problem,
  Proposal,
  Scene,
} from '../types';
import { createMockServer } from './server';

const body = <T>(res: { status: number; body: unknown }, status = 200): T => {
  expect(res.status).toBe(status);
  return res.body as T;
};
const code = (res: { status: number; body: unknown }) => (res.body as Problem).code;

function setup() {
  const bus = createEventBus();
  const events: Envelope[] = [];
  bus.subscribe((e) => events.push(e));
  const server = createMockServer(bus);
  const scene = body<Scene>(server.handle('GET', '/scene'));
  const co = scene.companies[0];
  return { server, events, co };
}

describe('mock API: concept expansion', () => {
  it('suggests a branch under the root, stores it once and proposes it as suggestions', () => {
    const { server, co } = setup();
    const res = body<ExpansionResult>(server.handle('POST', `/concepts/${co.rootId}/expand`, {}));
    expect(res.llmOutcome).toBe('used');
    expect(res.expansionId).toBeTruthy();
    expect(res.drafts).toHaveLength(5);
    expect(res.notes.map((n) => n.requires)).toEqual([[], [0], [], [], [2, 3]]);
    expect(res.notes.map((n) => n.depth)).toEqual([1, 2, 1, 1, null]);

    const refused = server.handle('POST', `/expansions/${res.expansionId}/proposals`, { indexes: [1] });
    expect(refused.status).toBe(422);

    const made = body<Proposal[]>(server.handle('POST', `/expansions/${res.expansionId}/proposals`, { indexes: [0, 1, 2, 3, 4] }), 202);
    expect(made).toHaveLength(5);
    expect(made.every((p) => p.origin === 'suggestion' && p.originDetail === null)).toBe(true);
    expect(made[0].heading).toBe('New concept · Production · suggested');
    expect(made[0].why).toBe('Suggested by the model · 90% · Planning decides what it needs next');
    expect(made[4].type).toBe('relation');

    expect(code(server.handle('POST', `/expansions/${res.expansionId}/proposals`, { indexes: [0] }))).toBe('expansion_submitted');
  });

  it('skips existing labels with their descendants and refuses a pending concept', () => {
    const { server, co } = setup();
    const first = body<ExpansionResult>(server.handle('POST', `/concepts/${co.rootId}/expand`, { depth: 1 }));
    expect(first.drafts).toHaveLength(4);
    const [planning] = body<Proposal[]>(server.handle('POST', `/expansions/${first.expansionId}/proposals`, { indexes: [0] }), 202);
    const again = body<ExpansionResult>(server.handle('POST', `/concepts/${co.rootId}/expand`, {}));
    expect(again.skipped).toEqual([
      { label: 'Northwind Industries planning', reason: 'existing_label' },
      { label: 'Northwind Industries schedule', reason: 'parent_skipped' },
    ]);
    expect(code(server.handle('POST', `/concepts/${planning.conceptId}/expand`, {}))).toBe('concept_pending');
  });

  it('answers no drafts when the token cap is 0', () => {
    const { server, co } = setup();
    server.handle('PATCH', '/settings', { llmMonthlyTokenCap: 0 });
    const res = body<ExpansionResult>(server.handle('POST', `/concepts/${co.rootId}/expand`, {}));
    expect(res).toMatchObject({ expansionId: null, llmOutcome: 'budget_exhausted', degraded: true, drafts: [] });
  });
});

describe('mock API: branch approval', () => {
  it('counts the open proposals below a concept and approves the branch parents first', () => {
    const { server, co } = setup();
    const res = body<ExpansionResult>(server.handle('POST', `/concepts/${co.rootId}/expand`, {}));
    const made = body<Proposal[]>(server.handle('POST', `/expansions/${res.expansionId}/proposals`, { indexes: [0, 1, 2, 3, 4] }), 202);
    const open = body<{ items: Proposal[] }>(server.handle('GET', '/proposals')).items;
    const byId = new Map(open.map((p) => [p.id, p]));
    expect(byId.get(made[0].id)?.openBelow).toBe(1);
    expect(byId.get(made[2].id)?.openBelow).toBe(0);
    expect(byId.get(made[4].id)?.openBelow).toBe(0);

    expect(code(server.handle('POST', `/proposals/${made[4].id}/approve-branch`))).toBe('branch_root_invalid');
    const result = body<BranchResult>(server.handle('POST', `/proposals/${made[0].id}/approve-branch`));
    expect(result).toEqual({ rootId: made[0].id, approved: 2, skipped: 0, remaining: 0, batches: 2, complete: true });
    const left = body<{ items: Proposal[] }>(server.handle('GET', '/proposals')).items.map((p) => p.id);
    expect(left).toEqual([made[2].id, made[3].id, made[4].id]);
  });
});

describe('mock API: whole-document extraction', () => {
  async function imported(server: ReturnType<typeof createMockServer>, text: string): Promise<ImportResult> {
    const res = await server.importDocument({ name: 'plant.txt', type: 'text/plain', bytes: new TextEncoder().encode(text) });
    return body<ImportResult>(res);
  }

  it('runs a job to a tree of document proposals, once per import', async () => {
    const { server, events, co } = setup();
    const imp = await imported(server, 'The plant runs production lines.\nEach production line uses machines.\n');
    const job = body<DocumentExtraction>(server.handle('POST', `/import/${imp.importId}/extraction`, { companyId: co.id }), 202);
    expect(job.state).toBe('queued');
    expect(code(server.handle('POST', `/import/${imp.importId}/extraction`, { companyId: co.id }))).toBe('extraction_exists');
    expect(code(server.handle('GET', `/extractions/${job.id}/result`))).toBe('extraction_not_ready');

    expect(body<DocumentExtraction>(server.handle('GET', `/extractions/${job.id}`)).state).toBe('running');
    const done = body<DocumentExtraction>(server.handle('GET', `/extractions/${job.id}`));
    expect(done.state).toBe('succeeded');
    const result = body<DocumentExtractionResult>(server.handle('GET', `/extractions/${job.id}/result`));
    expect(result.drafts.length).toBe(done.draftCount);
    expect(result.drafts.length).toBeGreaterThan(1);

    const made = body<Proposal[]>(
      server.handle('POST', `/extractions/${job.id}/proposals`, { indexes: result.drafts.map((_, i) => i) }),
      202,
    );
    expect(made.every((p) => p.origin === 'document' && p.originDetail?.fileName === 'plant.txt')).toBe(true);
    expect(code(server.handle('POST', `/extractions/${job.id}/proposals`, { indexes: [0] }))).toBe('extraction_submitted');
    expect(events.filter((e) => e.type === 'extraction.changed').map((e) => (e.payload.extraction as DocumentExtraction).state)).toEqual([
      'queued',
      'running',
      'succeeded',
    ]);
  });

  it('cancels a queued job and keeps one queued or running job at a time', async () => {
    const { server, co } = setup();
    const a = await imported(server, 'The plant runs production lines.\n');
    const b = await imported(server, 'The warehouse stores pallets today.\n');
    const job = body<DocumentExtraction>(server.handle('POST', `/import/${a.importId}/extraction`, { companyId: co.id }), 202);
    expect(code(server.handle('POST', `/import/${b.importId}/extraction`, { companyId: co.id }))).toBe('extraction_running');
    expect(body<DocumentExtraction>(server.handle('DELETE', `/extractions/${job.id}`), 202).state).toBe('cancelled');
    expect(body<DocumentExtraction>(server.handle('POST', `/import/${b.importId}/extraction`, { companyId: co.id }), 202).state).toBe(
      'queued',
    );
  });
});
