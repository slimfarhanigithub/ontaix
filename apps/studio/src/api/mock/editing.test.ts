import { DOMAIN_TEMPLATES } from '../../canvas/constants';
import { createEventBus, type Envelope } from '../events';
import type { Company, DecisionResult, DeletionImpact, Problem, Proposal, Scene, TenantDomain } from '../types';
import { createMockServer, type MockServer } from './server';

const body = <T>(res: { status: number; body: unknown }, status = 200): T => {
  expect(res.status).toBe(status);
  return res.body as T;
};

const code = (res: { status: number; body: unknown }, status: number): string => {
  expect(res.status).toBe(status);
  return (res.body as Problem).code;
};

/** The home company with `Plant` approved and `Production line` pending under it. */
function seeded(): { server: MockServer; events: Envelope[]; co: Company; plant: Proposal; line: Proposal } {
  const bus = createEventBus();
  const events: Envelope[] = [];
  bus.subscribe((e) => events.push(e));
  const server = createMockServer(bus);
  const co = body<Scene>(server.handle('GET', '/scene')).companies[0];
  const plant = body<Proposal>(
    server.handle('POST', '/proposals', { type: 'concept', companyId: co.id, parentId: co.rootId, label: 'Plant', domainKey: 'production', action: 'operates' }),
    202,
  );
  body<DecisionResult>(server.handle('POST', `/proposals/${plant.id}/approve`));
  const line = body<Proposal>(
    server.handle('POST', '/proposals', { type: 'concept', companyId: co.id, parentId: plant.conceptId, label: 'Production line', domainKey: 'production', action: 'runs' }),
    202,
  );
  return { server, events, co, plant, line };
}

describe('mock API: editing a pending draft (PATCH /proposals/{id})', () => {
  it('changes label and action in place, increments the revision and emits proposal.changed', () => {
    const { server, events, line } = seeded();
    expect(line.revision).toBe(0);
    const edited = body<Proposal>(server.handle('PATCH', `/proposals/${line.id}`, { revision: 0, label: 'Assembly line', action: 'operates' }));
    expect(edited.id).toBe(line.id);
    expect(edited.revision).toBe(1);
    expect(edited.title).toBe('Assembly line');
    expect(edited.html).toBe('<b>Assembly line</b> <em>· Plant <b>operates</b> Assembly line</em>');
    expect(edited.artefacts?.concepts?.[0].label).toBe('Assembly line');
    expect(edited.artefacts?.relations?.[0].label).toBe('operates');
    expect(events.map((e) => e.type).slice(-2)).toEqual(['proposal.changed', 'concept.changed']);
    const open = body<{ items: Proposal[] }>(server.handle('GET', '/proposals')).items;
    expect(open.map((p) => [p.title, p.revision])).toEqual([['Assembly line', 1]]);
    const scene = body<Scene>(server.handle('GET', '/scene'));
    expect(scene.nodes.map((n) => n.label)).toContain('Assembly line');
  });

  it('rewrites the deps and waitFor of dependants that named the old label', () => {
    const { server, co, line } = seeded();
    const child = body<Proposal>(
      server.handle('POST', '/proposals', { type: 'concept', companyId: co.id, parentId: line.conceptId, label: 'Machine', domainKey: 'production', action: 'has' }),
      202,
    );
    expect(child.waitFor).toBe('Production line');
    body<Proposal>(server.handle('PATCH', `/proposals/${line.id}`, { revision: 0, label: 'Assembly line' }));
    const after = body<Proposal>(server.handle('GET', `/proposals/${child.id}`));
    expect(after.deps).toEqual(['Assembly line']);
    expect(after.waitFor).toBe('Assembly line');
    expect(after.parentLabel).toBe('Assembly line');
    expect(after.html).toContain('Assembly line');
    // Approving the renamed parent still readies the child.
    body<DecisionResult>(server.handle('POST', `/proposals/${line.id}/approve`));
    expect(body<Proposal>(server.handle('GET', `/proposals/${child.id}`)).ready).toBe(true);
  });

  it('refuses a stale revision, a decided or change proposal, a duplicate label and a structural action', () => {
    const { server, co, plant, line } = seeded();
    body<Proposal>(server.handle('PATCH', `/proposals/${line.id}`, { revision: 0, label: 'Assembly line' }));
    expect(code(server.handle('PATCH', `/proposals/${line.id}`, { revision: 0, label: 'Other' }), 409)).toBe('proposal_changed');
    expect(code(server.handle('PATCH', `/proposals/${plant.id}`, { revision: 0, label: 'Site' }), 409)).toBe('proposal_not_editable');
    const rename = body<Proposal>(
      server.handle('POST', '/proposals', { type: 'change', changeKind: 'rename', payload: { conceptId: plant.conceptId, newLabel: 'Site' } }),
      202,
    );
    expect(code(server.handle('PATCH', `/proposals/${rename.id}`, { revision: 0, label: 'Works' }), 409)).toBe('proposal_not_editable');
    expect(code(server.handle('PATCH', `/proposals/${line.id}`, { revision: 1, label: 'Plant' }), 409)).toBe('duplicate_label');
    expect(code(server.handle('PATCH', `/proposals/${line.id}`, { revision: 1 }), 422)).toBe('validation_failed');
    expect(code(server.handle('PATCH', `/proposals/${line.id}`, { revision: 1, label: '<b>x</b>' }), 422)).toBe('validation_failed');
    const rel = body<Proposal>(server.handle('POST', '/proposals', { type: 'relation', aId: plant.conceptId, bId: co.rootId, action: 'belongs to' }), 202);
    expect(code(server.handle('PATCH', `/proposals/${rel.id}`, { revision: 0, action: 'is a' }), 422)).toBe('validation_failed');
    const edited = body<Proposal>(server.handle('PATCH', `/proposals/${rel.id}`, { revision: 0, action: 'reports to' }));
    expect(edited.title).toBe('Plant reports to Northwind Industries');
    expect(edited.artefacts?.relations?.[0].label).toBe('reports to');
  });

  it('approval carries expectedRevision and refuses a draft edited since', () => {
    const { server, line } = seeded();
    expect(code(server.handle('POST', `/proposals/${line.id}/approve?expectedRevision=1`), 409)).toBe('proposal_changed');
    body<Proposal>(server.handle('PATCH', `/proposals/${line.id}`, { revision: 0, label: 'Assembly line' }));
    expect(code(server.handle('POST', `/proposals/${line.id}/approve?expectedRevision=0`), 409)).toBe('proposal_changed');
    const ok = body<DecisionResult>(server.handle('POST', `/proposals/${line.id}/approve?expectedRevision=1`));
    expect(ok.proposal.state).toBe('approved');
    expect(ok.artefacts.concepts?.[0].label).toBe('Assembly line');
  });
});

describe('mock API: tenant domains', () => {
  it('lists the nine templates in ring order', () => {
    const server = createMockServer(createEventBus());
    const domains = body<TenantDomain[]>(server.handle('GET', '/domains'));
    expect(domains.map((d) => d.key)).toEqual(DOMAIN_TEMPLATES.map((t) => t.key));
    expect(domains[0]).toMatchObject({ name: 'Production', owner: 'Plant operations', color: '#d30c55', defaultColor: '#d30c55', template: true, position: 0, revision: 0 });
  });

  it('creates a domain through a proposal; its product joins a company when the first concept does', () => {
    const { server, events, co, plant } = seeded();
    const p = body<Proposal>(server.handle('POST', '/domains', { name: 'Sustainability', color: '#112233', owner: 'Facilities' }), 202);
    expect(p).toMatchObject({ type: 'change', changeKind: 'create_domain', title: 'New domain Sustainability', companyId: null });
    expect(body<TenantDomain[]>(server.handle('GET', '/domains'))).toHaveLength(9);
    body<DecisionResult>(server.handle('POST', `/proposals/${p.id}/approve`));
    const domains = body<TenantDomain[]>(server.handle('GET', '/domains'));
    expect(domains).toHaveLength(10);
    expect(domains[9]).toMatchObject({ key: 'sustainability', name: 'Sustainability', owner: 'Facilities', color: '#112233', template: false, position: 9 });
    const changed = events.find((e) => e.type === 'domain.changed');
    expect(changed?.payload).toMatchObject({ created: true, domain: { key: 'sustainability' } });
    let scene = body<Scene>(server.handle('GET', '/scene'));
    expect(scene.companies[0].domainProducts).toHaveLength(9);
    expect(scene.appearance.colors.sustainability).toBe('#112233');
    const solar = body<Proposal>(
      server.handle('POST', '/proposals', { type: 'concept', companyId: co.id, parentId: plant.conceptId, label: 'Solar roof', domainKey: 'sustainability', action: 'has' }),
      202,
    );
    expect(solar.heading).toBe('New concept · Sustainability');
    expect(solar.artefacts?.concepts?.[0].color).toBe('#112233');
    scene = body<Scene>(server.handle('GET', '/scene'));
    expect(scene.companies[0].domainProducts.map((d) => d.key)).toContain('sustainability');
    // A key the tenant lacks is 422.
    expect(code(server.handle('POST', '/proposals', { type: 'concept', companyId: co.id, parentId: co.rootId, label: 'Nope', domainKey: 'nowhere', action: 'has' }), 422)).toBe(
      'validation_failed',
    );
  });

  it('refuses a duplicate name and the 65th domain', () => {
    const server = createMockServer(createEventBus());
    expect(code(server.handle('POST', '/domains', { name: 'sales', color: '#112233' }), 409)).toBe('duplicate_label');
    expect(code(server.handle('POST', '/domains', { name: 'Fresh', color: 'blue' }), 422)).toBe('validation_failed');
    for (let i = 0; i < 55; i++) {
      const p = body<Proposal>(server.handle('POST', '/domains', { name: `Domain ${i}`, color: '#112233' }), 202);
      body<DecisionResult>(server.handle('POST', `/proposals/${p.id}/approve`));
    }
    expect(body<TenantDomain[]>(server.handle('GET', '/domains'))).toHaveLength(64);
    expect(code(server.handle('POST', '/domains', { name: 'One more', color: '#112233' }), 409)).toBe('domain_limit');
  });

  it('renames, recolours and re-owns a domain in every company on approval', () => {
    const { server, events, co, plant } = seeded();
    body<{ company: Company }>(server.handle('POST', '/companies', { name: 'Aurora Valves', sub: '', start: 'one_cell' }), 201);
    expect(code(server.handle('PATCH', '/domains/nowhere', { name: 'X' }), 404)).toBe('not_found');
    expect(code(server.handle('PATCH', '/domains/production', {}), 422)).toBe('validation_failed');
    expect(code(server.handle('PATCH', '/domains/production', { name: 'Sales' }), 409)).toBe('duplicate_label');
    const p = body<Proposal>(server.handle('PATCH', '/domains/production', { name: 'Manufacturing', color: '#abcdef', owner: 'Works' }), 202);
    expect(p).toMatchObject({ changeKind: 'edit_domain', title: 'Edit domain Production' });
    const res = body<DecisionResult>(server.handle('POST', `/proposals/${p.id}/approve`));
    expect(res.artefacts.domainProducts?.map((d) => [d.name, d.color, d.owner])).toEqual([
      ['Manufacturing', '#abcdef', 'Works'],
      ['Manufacturing', '#abcdef', 'Works'],
    ]);
    expect(events.map((e) => e.type)).toEqual(expect.arrayContaining(['domain.changed', 'appearance.changed']));
    const domains = body<TenantDomain[]>(server.handle('GET', '/domains'));
    expect(domains[0]).toMatchObject({ key: 'production', name: 'Manufacturing', owner: 'Works', color: '#abcdef', revision: 1 });
    const scene = body<Scene>(server.handle('GET', '/scene'));
    expect(scene.companies.every((c) => c.domainProducts[0].name === 'Manufacturing')).toBe(true);
    expect(scene.nodes.find((n) => n.id === plant.conceptId)).toMatchObject({ color: '#abcdef' });
    expect(scene.companies[0].id).toBe(co.id);
  });

  it('moves a concept to another domain through a proposal', () => {
    const { server, co, plant, line } = seeded();
    expect(code(server.handle('POST', `/concepts/${co.rootId}/move`, { domainKey: 'sales' }), 409)).toBe('root_concept');
    expect(code(server.handle('POST', `/concepts/${line.conceptId}/move`, { domainKey: 'sales' }), 409)).toBe('concept_pending');
    expect(code(server.handle('POST', `/concepts/${plant.conceptId}/move`, { domainKey: 'production' }), 422)).toBe('validation_failed');
    expect(code(server.handle('POST', `/concepts/${plant.conceptId}/move`, { domainKey: 'nowhere' }), 422)).toBe('validation_failed');
    const p = body<Proposal>(server.handle('POST', `/concepts/${plant.conceptId}/move`, { domainKey: 'sales' }), 202);
    expect(p).toMatchObject({ changeKind: 'move_concept_domain', title: 'Move Plant to Sales', conceptId: plant.conceptId });
    const res = body<DecisionResult>(server.handle('POST', `/proposals/${p.id}/approve`));
    expect(res.artefacts.concepts?.[0]).toMatchObject({ domainKey: 'sales', color: '#0e8a6a' });
    expect(res.artefacts.domainProducts?.map((d) => [d.key, d.revision]).sort()).toEqual([
      ['production', 2],
      ['sales', 1],
    ]);
  });
});

describe('mock API: deletion impact, bulk deletion, domain deletion, company removal', () => {
  /** Plant (approved) with Line and Machine under it, a relation to Client, and Aurora with one cell. */
  function model() {
    const { server, co, plant, line } = seeded();
    body<DecisionResult>(server.handle('POST', `/proposals/${line.id}/approve`));
    const machine = body<Proposal>(
      server.handle('POST', '/proposals', { type: 'concept', companyId: co.id, parentId: line.conceptId, label: 'Machine', domainKey: 'maintenance', action: 'has' }),
      202,
    );
    body<DecisionResult>(server.handle('POST', `/proposals/${machine.id}/approve`));
    const client = body<Proposal>(
      server.handle('POST', '/proposals', { type: 'concept', companyId: co.id, parentId: co.rootId, label: 'Client', domainKey: 'sales', action: 'serves' }),
      202,
    );
    body<DecisionResult>(server.handle('POST', `/proposals/${client.id}/approve`));
    const rel = body<Proposal>(server.handle('POST', '/proposals', { type: 'relation', aId: plant.conceptId, bId: client.conceptId, action: 'supplies' }), 202);
    body<DecisionResult>(server.handle('POST', `/proposals/${rel.id}/approve`));
    const aurora = body<{ company: Company; root: { id: string } }>(server.handle('POST', '/companies', { name: 'Aurora Valves', sub: '', start: 'one_cell' }), 201);
    const valve = body<Proposal>(
      server.handle('POST', '/proposals', { type: 'concept', companyId: aurora.company.id, parentId: aurora.company.rootId, label: 'Valve', domainKey: 'production', action: 'makes' }),
      202,
    );
    body<DecisionResult>(server.handle('POST', `/proposals/${valve.id}/approve`));
    const same = body<Proposal>(server.handle('POST', '/proposals', { type: 'relation', aId: valve.conceptId, bId: plant.conceptId, action: 'equivalent to' }), 202);
    body<DecisionResult>(server.handle('POST', `/proposals/${same.id}/approve`));
    return { server, co, plant, line, machine, client, aurora: aurora.company, valve };
  }

  it('names what a concept deletion, a domain deletion and a company removal would remove', () => {
    const { server, co, plant, aurora } = model();
    const one = body<DeletionImpact>(server.handle('POST', '/deletion-impact', { companyId: co.id, conceptIds: [plant.conceptId] }));
    expect(one).toMatchObject({ concepts: 1, descendants: 2, relations: 5, crossCompanyRelations: 1, bindings: 0, attributes: 0, sources: 0, cascadedProposals: 0 });
    expect(one.names).toEqual(['Plant', 'Production line', 'Machine']);
    const production = body<Scene>(server.handle('GET', '/scene')).companies[0].domainProducts.find((d) => d.key === 'production');
    const dom = body<DeletionImpact>(server.handle('POST', '/deletion-impact', { companyId: co.id, domainProductIds: [production?.id] }));
    expect(dom).toMatchObject({ concepts: 2, descendants: 1, relations: 5, crossCompanyRelations: 1 });
    const whole = body<DeletionImpact>(server.handle('POST', '/deletion-impact', { companyId: aurora.id, wholeCompany: true }));
    expect(whole).toMatchObject({ concepts: 1, descendants: 0, relations: 2, crossCompanyRelations: 1, sources: 0, cascadedProposals: 0 });
    body<Proposal>(server.handle('POST', '/proposals', { type: 'concept', companyId: aurora.id, parentId: aurora.rootId, label: 'Seat', domainKey: 'production', action: 'has' }), 202);
    const withDraft = body<DeletionImpact>(server.handle('POST', '/deletion-impact', { companyId: aurora.id, wholeCompany: true }));
    expect(withDraft).toMatchObject({ concepts: 1, relations: 2, cascadedProposals: 1 });
    expect(code(server.handle('POST', '/deletion-impact', { companyId: co.id, conceptIds: [co.rootId] }), 409)).toBe('root_concept');
    expect(code(server.handle('POST', '/deletion-impact', { companyId: co.id, conceptIds: [plant.conceptId, plant.conceptId] }), 422)).toBe('validation_failed');
    expect(code(server.handle('POST', '/deletion-impact', { companyId: 'nope', conceptIds: [] }), 404)).toBe('not_found');
  });

  it('bulk-deletes concepts and domain products of one company, all at once on approval', () => {
    const { server, co, plant, client, valve } = model();
    expect(code(server.handle('POST', '/proposals/bulk-delete', { companyId: co.id, conceptIds: [plant.conceptId, valve.conceptId] }), 422)).toBe('validation_failed');
    expect(code(server.handle('POST', '/proposals/bulk-delete', { companyId: co.id }), 422)).toBe('validation_failed');
    expect(code(server.handle('POST', '/proposals/bulk-delete', { companyId: co.id, conceptIds: [co.rootId] }), 409)).toBe('root_concept');
    const sales = body<Scene>(server.handle('GET', '/scene')).companies[0].domainProducts.find((d) => d.key === 'sales');
    const p = body<Proposal>(server.handle('POST', '/proposals/bulk-delete', { companyId: co.id, conceptIds: [plant.conceptId], domainProductIds: [sales?.id] }), 202);
    expect(p).toMatchObject({ changeKind: 'delete_bulk', title: 'Delete 1 concept and 1 domain product' });
    expect(p.html).toBe(
      'Delete 1 concept and 1 domain product of Northwind Industries: 2 concepts (Plant, Client, Production line, Machine), 2 descendants, 6 relations (1 cross-company), 0 bindings, 0 attributes',
    );
    const res = body<DecisionResult>(server.handle('POST', `/proposals/${p.id}/approve`));
    expect(res.artefacts.concepts?.map((c) => c.label).sort()).toEqual(['Client', 'Machine', 'Plant', 'Production line']);
    expect(res.artefacts.concepts?.every((c) => c.dyingAt)).toBe(true);
    expect(res.artefacts.relations?.every((r) => r.dyingAt)).toBe(true);
    const scene = body<Scene>(server.handle('GET', '/scene'));
    expect(scene.nodes.filter((n) => n.companyId === co.id).map((n) => n.label)).toEqual(['Northwind Industries']);
    expect(scene.nodes.map((n) => n.label)).toContain('Valve');
    // Only Aurora's birth line is left.
    expect(scene.links).toHaveLength(1);
    expect(client.conceptId).toBeTruthy();
  });

  it('deletes one company domain product with its concepts and descendants of any domain', () => {
    const { server, machine } = model();
    const production = body<Scene>(server.handle('GET', '/scene')).companies[0].domainProducts.find((d) => d.key === 'production');
    expect(code(server.handle('DELETE', '/domain-products/nope'), 404)).toBe('not_found');
    const p = body<Proposal>(server.handle('DELETE', `/domain-products/${production?.id}`), 202);
    expect(p).toMatchObject({ changeKind: 'delete_domain', title: 'Delete Production of Northwind Industries', domainProductId: production?.id });
    body<DecisionResult>(server.handle('POST', `/proposals/${p.id}/approve`));
    const scene = body<Scene>(server.handle('GET', '/scene'));
    expect(scene.nodes.map((n) => n.label).sort()).toEqual(['Aurora Valves', 'Client', 'Northwind Industries', 'Valve']);
    expect(scene.nodes.find((n) => n.id === machine.conceptId)).toBeUndefined();
    expect(body<TenantDomain[]>(server.handle('GET', '/domains'))).toHaveLength(9);
  });

  it('removes a company completely, naming the impact and rejecting its open proposals by cascade', () => {
    const { server, co, aurora, valve } = model();
    body<Proposal>(server.handle('POST', '/proposals', { type: 'concept', companyId: aurora.id, parentId: valve.conceptId, label: 'Seat', domainKey: 'production', action: 'has' }), 202);
    expect(code(server.handle('DELETE', `/companies/${co.id}`), 409)).toBe('home_company');
    const p = body<Proposal>(server.handle('DELETE', `/companies/${aurora.id}`), 202);
    expect(p.html).toBe('Remove <b>Aurora Valves</b> from the portfolio with its 1 concept (Valve), 0 descendants, 2 relations (1 cross-company), 0 sources, 0 bindings, 0 attributes');
    const res = body<DecisionResult>(server.handle('POST', `/proposals/${p.id}/approve`));
    expect(res.proposal.state).toBe('approved');
    const scene = body<Scene>(server.handle('GET', '/scene'));
    expect(scene.companies.map((c) => c.name)).toEqual(['Northwind Industries']);
    expect(scene.nodes.map((n) => n.label)).not.toContain('Valve');
    expect(scene.links.some((l) => 'kind' in l && l.kind === 'same')).toBe(false);
    expect(scene.proposals).toHaveLength(0);
  });
});

describe('mock API: company creation setting', () => {
  it('refuses POST /companies while companyCreation is off', () => {
    const server = createMockServer(createEventBus());
    expect(body<Scene>(server.handle('GET', '/scene')).settings.companyCreation).toBe(true);
    server.handle('PATCH', '/settings', { companyCreation: false });
    expect(code(server.handle('POST', '/companies', { name: 'Aurora Valves', start: 'one_cell' }), 409)).toBe('company_creation_disabled');
    server.handle('PATCH', '/settings', { companyCreation: true });
    body(server.handle('POST', '/companies', { name: 'Aurora Valves', start: 'one_cell' }), 201);
  });
});
