import { createEventBus, type Envelope } from '../events';
import type { AuditEntry, DecisionResult, ImportResult, Page, Proposal, Scene, TeachResult } from '../types';
import { createMockServer } from './server';

const body = <T>(res: { status: number; body: unknown }, status = 200): T => {
  expect(res.status).toBe(status);
  return res.body as T;
};

describe('mock API: propose, pending, approve, reject', () => {
  it('serves the fresh home company from GET /scene', () => {
    const server = createMockServer(createEventBus());
    const scene = body<Scene>(server.handle('GET', '/scene'));
    expect(scene.companies).toHaveLength(1);
    expect(scene.companies[0].name).toBe('Northwind Industries');
    expect(scene.companies[0].domainProducts).toHaveLength(9);
    expect(scene.nodes).toHaveLength(1);
    expect(scene.proposals).toHaveLength(0);
    expect(scene.settings.approvalRequired).toBe(true);
    expect(scene.viewState).toEqual({ coverage: false });
    expect(scene).not.toHaveProperty('demoStory');
  });

  it('a concept proposal creates a pending cell and birth relation, blocked until its parent is approved', () => {
    const bus = createEventBus();
    const events: Envelope[] = [];
    bus.subscribe((e) => events.push(e));
    const server = createMockServer(bus);
    const scene = body<Scene>(server.handle('GET', '/scene'));
    const co = scene.companies[0];
    const plant = body<Proposal>(
      server.handle('POST', '/proposals', {
        type: 'concept',
        companyId: co.id,
        parentId: co.rootId,
        label: 'Plant',
        domainKey: 'production',
        action: 'operates',
        caption: 'Plant is kept in Production.',
      }),
      202,
    );
    expect(plant.state).toBe('pending');
    expect(plant.ready).toBe(true);
    expect(plant.heading).toBe('New concept · Production');
    expect(plant.html).toBe('<b>Plant</b> <em>· Northwind Industries <b>operates</b> Plant</em>');
    expect(plant.artefacts?.concepts?.[0].pending).toBe(true);
    expect(plant.artefacts?.relations?.[0]).toMatchObject({ kind: 'rel', label: 'operates', rest: 330, pending: true });
    expect(events.map((e) => e.type)).toEqual(['proposal.created']);

    const line = body<Proposal>(
      server.handle('POST', '/proposals', {
        type: 'concept',
        companyId: co.id,
        parentId: plant.conceptId,
        label: 'Production line',
        domainKey: 'production',
        action: 'runs',
      }),
      202,
    );
    expect(line.ready).toBe(false);
    expect(line.waitFor).toBe('Plant');
    expect(server.handle('POST', `/proposals/${line.id}/approve`).status).toBe(409);

    const decision = body<DecisionResult>(server.handle('POST', `/proposals/${plant.id}/approve`));
    expect(decision.proposal.state).toBe('approved');
    expect(decision.artefacts.concepts?.[0].pending).toBe(false);
    expect(decision.artefacts.domainProducts?.[0]).toMatchObject({ key: 'production', revision: 1, version: 'v1.1' });
    expect(decision.caption).toBe('Plant is kept in Production.');
    expect(events.at(-1)?.type).toBe('proposal.approved');

    const open = body<Page & { items: Proposal[] }>(server.handle('GET', '/proposals'));
    expect(open.items).toHaveLength(1);
    expect(open.items[0].ready).toBe(true);
  });

  it('rejecting a parent cascades to the proposals born from it and removes the cells', () => {
    const server = createMockServer(createEventBus());
    const scene = body<Scene>(server.handle('GET', '/scene'));
    const co = scene.companies[0];
    const plant = body<Proposal>(
      server.handle('POST', '/proposals', { type: 'concept', companyId: co.id, parentId: co.rootId, label: 'Plant', domainKey: 'production', action: 'operates' }),
      202,
    );
    const line = body<Proposal>(
      server.handle('POST', '/proposals', { type: 'concept', companyId: co.id, parentId: plant.conceptId, label: 'Production line', domainKey: 'production', action: 'runs' }),
      202,
    );
    const decision = body<DecisionResult>(server.handle('POST', `/proposals/${plant.id}/reject`));
    expect(decision.proposal.state).toBe('rejected');
    expect(decision.cascaded.map((p) => p.id)).toEqual([line.id]);
    expect(decision.caption).toBe('Plant was not kept. The model only holds what its owners approved.');
    const after = body<Scene>(server.handle('GET', '/scene'));
    expect(after.nodes).toHaveLength(1);
    expect(after.links).toHaveLength(0);
    expect(after.proposals).toHaveLength(0);
  });

  it('approve-all loops until nothing is ready and refuses a cross-company relation when the switch is off', () => {
    const server = createMockServer(createEventBus());
    const scene = body<Scene>(server.handle('GET', '/scene'));
    const co = scene.companies[0];
    const plant = body<Proposal>(
      server.handle('POST', '/proposals', { type: 'concept', companyId: co.id, parentId: co.rootId, label: 'Plant', domainKey: 'production', action: 'operates' }),
      202,
    );
    body<Proposal>(
      server.handle('POST', '/proposals', { type: 'concept', companyId: co.id, parentId: plant.conceptId, label: 'Production line', domainKey: 'production', action: 'runs' }),
      202,
    );
    const bulk = body<{ approved: number; rounds: number; remaining: number }>(server.handle('POST', '/proposals/approve-all'));
    expect(bulk).toMatchObject({ approved: 2, rounds: 2, remaining: 0 });

    const aurora = body<{ company: { id: string; rootId: string }; proposals: Proposal[] }>(
      server.handle('POST', '/companies', { name: 'Aurora Valves', sub: 'industrial valves', start: 'starter_vocabulary' }),
      201,
    );
    expect(aurora.proposals).toHaveLength(13);
    server.handle('PATCH', '/settings', { crossCompany: false });
    const refused = server.handle('POST', '/proposals', {
      type: 'relation',
      aId: aurora.proposals[0].conceptId,
      bId: plant.conceptId,
      action: 'equivalent to',
    });
    expect(refused.status).toBe(409);
    expect((refused.body as { code: string }).code).toBe('cross_company_disabled');
  });
});

describe('mock API: drafts in the contract shape', () => {
  it('refuses a relation end given by both id and label with the same 422 as the API', () => {
    const server = createMockServer(createEventBus());
    const scene = body<Scene>(server.handle('GET', '/scene'));
    const root = scene.companies[0].rootId;
    const mixed = { type: 'relation', aId: root, bId: root, aLabel: 'Northwind Industries', action: 'runs' };

    const single = server.handle('POST', '/proposals', mixed);
    const batch = server.handle('POST', '/proposals/batch', { drafts: [mixed] });

    for (const res of [single, batch]) {
      expect(res.status).toBe(422);
      expect(res.body).toMatchObject({ code: 'validation_failed', detail: 'exactly one of aId or aLabel is required' });
    }
    expect(body<Scene>(server.handle('GET', '/scene')).proposals).toHaveLength(0);
  });
});

describe('mock API: text, speech and document origins', () => {
  const fresh = () => {
    const server = createMockServer(createEventBus());
    const co = body<Scene>(server.handle('GET', '/scene')).companies[0];
    return { server, co };
  };
  const upload = (name: string, text: string, type = 'text/plain') => ({ name, type, bytes: new TextEncoder().encode(text) });
  const code = (res: { body: unknown }) => (res.body as { code: string }).code;

  it('a typed sentence and a speech transcript become proposals with their declared origin', () => {
    const { server, co } = fresh();
    const typed = body<TeachResult>(server.handle('POST', '/teach/parse', { companyId: co.id, text: 'A plant has production lines' }));
    expect(typed).toMatchObject({ outcome: 'understood', origin: 'text', originDetail: null });
    expect(typed.drafts.every((d) => d.origin === 'text')).toBe(true);
    const made = body<Proposal[]>(server.handle('POST', '/proposals/batch', { drafts: typed.drafts }), 202);
    expect(made.map((p) => [p.origin, p.originDetail])).toEqual([
      ['text', null],
      ['text', null],
    ]);

    const spoken = body<TeachResult>(server.handle('POST', '/teach/parse', { companyId: co.id, text: 'Invoices have due dates', origin: 'speech' }));
    expect(spoken.origin).toBe('speech');
    const said = body<Proposal[]>(server.handle('POST', '/proposals/batch', { drafts: spoken.drafts }), 202);
    expect(said.every((p) => p.origin === 'speech')).toBe(true);

    body(server.handle('POST', `/proposals/${made[0].id}/approve`));
    const audit = body<Page & { items: AuditEntry[] }>(server.handle('GET', '/audit'));
    expect(audit.items.find((e) => e.proposalId === made[0].id)?.origin).toBe('text');
  });

  it('the settings gate each channel with 409 channel_disabled', async () => {
    const { server, co } = fresh();
    server.handle('PATCH', '/settings', { voice: false });
    expect(code(server.handle('POST', '/teach/parse', { companyId: co.id, text: 'A plant has lines', origin: 'speech' }))).toBe('channel_disabled');
    const draft = { type: 'concept', companyId: co.id, parentId: co.rootId, label: 'Plant', domainKey: 'production', action: 'operates', origin: 'speech' };
    expect(code(server.handle('POST', '/proposals', draft))).toBe('channel_disabled');
    server.handle('PATCH', '/settings', { liveTeaching: false });
    expect(code(server.handle('POST', '/teach/parse', { companyId: co.id, text: 'A plant has lines' }))).toBe('channel_disabled');
    server.handle('PATCH', '/settings', { importDocs: false });
    expect(code(await server.importDocument(upload('plants.txt', 'Every plant runs production lines.')))).toBe('channel_disabled');
  });

  it('a document import is stored; each cited sentence is parsed at most three times and drafted by one call', async () => {
    const { server, co } = fresh();
    const imported = body<ImportResult>(
      await server.importDocument(upload('reports/2026/plants.txt','Every plant runs production lines. Short one. A machine has sensors!')),
    );
    expect(imported).toMatchObject({
      fileName: 'plants.txt',
      origin: 'document',
      originDetail: { fileName: 'plants.txt', mediaType: 'text/plain' },
      sentences: ['Every plant runs production lines.', 'A machine has sensors!'],
    });
    const importRef = { importId: imported.importId, sentenceIndex: 0 };
    const parsed = body<TeachResult>(server.handle('POST', '/teach/parse', { companyId: co.id, importRef, origin: 'speech' }));
    expect(parsed).toMatchObject({ outcome: 'understood', origin: 'document', originDetail: { fileName: 'plants.txt', sentenceIndex: 0 } });
    expect(parsed.drafts.every((d) => d.importRef?.sentenceIndex === 0)).toBe(true);

    const made = body<Proposal[]>(server.handle('POST', '/proposals/batch', { drafts: parsed.drafts }), 202);
    expect(made.map((p) => p.origin)).toEqual(['document', 'document']);
    expect(made[0].originDetail).toEqual({ fileName: 'plants.txt', mediaType: 'text/plain', sentenceIndex: 0 });
    expect(code(server.handle('POST', '/proposals/batch', { drafts: parsed.drafts }))).toBe('import_sentence_used');

    server.handle('POST', '/teach/parse', { companyId: co.id, importRef });
    server.handle('POST', '/teach/parse', { companyId: co.id, importRef });
    expect(code(server.handle('POST', '/teach/parse', { companyId: co.id, importRef }))).toBe('import_sentence_used');
    expect(server.handle('POST', '/teach/parse', { companyId: co.id, importRef: { importId: 'nope', sentenceIndex: 0 } }).status).toBe(404);
  });

  it('refuses bad file names, unknown media types, and an expired import with 410', async () => {
    const { server, co } = fresh();
    expect((await server.importDocument(upload('a\u202Etxt.exe', 'Every plant runs lines.'))).status).toBe(422);
    expect((await server.importDocument(upload('notes.bin', 'Every plant runs lines.', 'application/octet-stream'))).status).toBe(415);
    const imported = body<ImportResult>(await server.importDocument(upload('plants.md', 'Every plant runs production lines.')));
    vi.useFakeTimers({ now: Date.now() + 61 * 60 * 1000, toFake: ['Date'] });
    try {
      const res = server.handle('POST', '/teach/parse', { companyId: co.id, importRef: { importId: imported.importId, sentenceIndex: 0 } });
      expect(res.status).toBe(410);
      expect(code(res)).toBe('import_expired');
    } finally {
      vi.useRealTimers();
    }
  });
});
