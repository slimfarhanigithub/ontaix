import { createEventBus } from '../events';
import type { CostSummary, Group, Page, RoleInfo, Scene, User } from '../types';
import { seedAgents, seedUsers } from './directory';
import { createMockServer } from './server';

type Paged<T> = Page & { items: T[] };

const body = <T,>(res: { status: number; body: unknown }, status = 200): T => {
  expect(res.status).toBe(status);
  return res.body as T;
};

describe('mock directory', () => {
  it('generates the reference users and agents deterministically', () => {
    const users = seedUsers();
    expect(users).toHaveLength(180);
    expect(seedUsers()).toEqual(users);
    expect(users.filter((u) => u.company === 'Aurora Valves')).toHaveLength(36);
    expect(users[0].email).toMatch(/@auroravalves\.com$/);
    const agents = seedAgents();
    expect(agents).toHaveLength(2400);
    expect(seedAgents()[1234]).toEqual(agents[1234]);
  });

  it('pages, searches, filters and sorts users as the contract describes', () => {
    const server = createMockServer(createEventBus());
    const all = body<Paged<User>>(server.handle('GET', '/users?page=1&pageSize=200'));
    expect(all.total).toBe(180);
    expect(all.items).toHaveLength(180);
    const second = body<Paged<User>>(server.handle('GET', '/users?page=2&pageSize=40'));
    expect(second.items[0].id).toBe(all.items[40].id);
    const it = body<Paged<User>>(server.handle('GET', '/users?filter[department]=IT&sort=name&order=desc'));
    expect(it.items.every((u) => u.department === 'IT')).toBe(true);
    expect(it.items.map((u) => u.name)).toEqual([...it.items.map((u) => u.name)].sort().reverse());
    expect(server.handle('GET', '/users?filter[shoe]=42').status).toBe(400);
    const everyone = all.items.every((u) => u.groups.some((g) => g.name === 'All employees'));
    expect(everyone).toBe(true);
  });

  it('keeps groups, members and role assignments, audited', () => {
    const server = createMockServer(createEventBus());
    const groups = body<Paged<Group>>(server.handle('GET', '/groups')).items;
    expect(groups.map((g) => g.name)).toEqual([
      'Plant operations · owners',
      'Procurement · builders',
      'Commercial · owners',
      'Governance board',
      'Data platform team',
      'All employees',
      'PE due-diligence team',
    ]);
    const g = body<Group>(server.handle('POST', '/groups', { name: 'Quality · owners', description: 'Owns Quality' }), 201);
    expect(server.handle('POST', '/groups', { name: '  ' }).status).toBe(422);
    const users = body<Paged<User>>(server.handle('GET', '/users?pageSize=200')).items;
    expect(server.handle('PUT', `/groups/${g.id}/members/${users[3].id}`).status).toBe(204);
    const withMember = body<Group>(server.handle('GET', `/groups/${g.id}`));
    expect(withMember.memberCount).toBe(1);
    const quality = { kind: 'domain', companyId: null, domainKey: 'quality', label: 'Quality' };
    body(server.handle('POST', `/groups/${g.id}/roles`, { role: 'owner', scope: quality }), 201);
    expect(server.handle('POST', `/groups/${g.id}/roles`, { role: 'owner', scope: quality }).status).toBe(409);
    expect(server.handle('POST', `/groups/${g.id}/roles`, { role: 'administrator', scope: quality }).status).toBe(422);
    const roles = body<RoleInfo[]>(server.handle('GET', '/roles'));
    expect(roles.map((r) => r.label)).toEqual(['Owner', 'Builder', 'Governor', 'Member', 'Administrator', 'Auditor', 'Agent']);
    expect(roles.find((r) => r.role === 'member')?.assigned).toBe(180);
    const audit = body<Paged<{ kind: string; what: string }>>(server.handle('GET', '/audit?pageSize=120')).items;
    expect(audit.slice(0, 3).map((e) => e.what)).toEqual([
      'Owner · Quality given to Quality · owners',
      `${users[3].name} added to Quality · owners`,
      'Quality · owners created',
    ]);
  });

  it('reports cost and toggles agent access', () => {
    const server = createMockServer(createEventBus());
    const cost = body<CostSummary>(server.handle('GET', '/cost'));
    expect(cost.agentsRegistered).toBe(2400);
    expect(cost.allocatedEur).toBe(Math.round((cost.measuredEur * 1.35) / 1000) * 1000 || 3000);
    expect(cost.byPlatform.map((p) => p.costEur)).toEqual([...cost.byPlatform.map((p) => p.costEur)].sort((a, b) => b - a));
    const page = body<Paged<{ id: string; access: boolean }>>(server.handle('GET', '/agents?pageSize=50'));
    expect(page.total).toBe(2400);
    const a = page.items[0];
    body(server.handle('PATCH', `/agents/${a.id}`, { access: !a.access }));
    const after = body<CostSummary>(server.handle('GET', '/cost'));
    expect(after.agentsWithAccess).toBe(cost.agentsWithAccess + (a.access ? -1 : 1));
  });

  it('disables companies-may-interact only with the typed confirmation', () => {
    const server = createMockServer(createEventBus());
    const scene = body<Scene>(server.handle('GET', '/scene'));
    expect(server.handle('POST', '/settings/cross-company/disable', { confirmation: 'yes' }).status).toBe(409);
    const res = body<{ removedRelations: number; settings: { crossCompany: boolean } }>(
      server.handle('POST', '/settings/cross-company/disable', { confirmation: 'disable' }),
    );
    expect(res.removedRelations).toBe(0);
    expect(res.settings.crossCompany).toBe(false);
    expect(scene.settings.crossCompany).toBe(true);
    expect(server.handle('PATCH', '/settings', { approvalRequired: false }).status).toBe(409);
  });
});
