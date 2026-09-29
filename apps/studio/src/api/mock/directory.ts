/**
 * The mock API's native directory and agent registry: users, groups with members and role
 * assignments, roles, scopes, agents and the monthly cost summary. Fixtures are generated with
 * the reference's own seeded generator (`seeded`, `USERS`, `defaultGroups`, `AGENTS`,
 * reference/ontaix-studio-reference.html lines 923-932), so the lists match it row for row.
 */
import { DOMAIN_TEMPLATES } from '../../canvas/constants';
import type * as T from '../types';

/** The reference's deterministic generator; independent of the random stream the canvas draws from. */
export function seeded(n: number): () => number {
  let x = n * 9301 + 49297;
  return () => (x = (x * 9301 + 49297) % 233280) / 233280;
}

export interface SeedUser {
  index: number;
  name: string;
  email: string;
  dept: string;
  company: string;
}

export function seedUsers(): SeedUser[] {
  const r = seeded(23);
  const first = ['Anna', 'Luca', 'Mehdi', 'Sofia', 'Jonas', 'Amira', 'Tomas', 'Ines', 'Karim', 'Elena', 'Pieter', 'Nadia', 'Marco', 'Leila', 'Oskar', 'Chloé', 'Yusuf', 'Greta', 'Sami', 'Julia', 'Hugo', 'Dalia', 'Nils', 'Rania', 'Felix', 'Aya', 'Bruno', 'Maya', 'Ivan', 'Zoe'];
  const last = ['Berg', 'Rossi', 'Haddad', 'Novak', 'Meyer', 'Dubois', 'Kaya', 'Lund', 'Ferreira', 'Schulz', 'Moreau', 'Costa', 'Weber', 'Petit', 'Nilsen', 'Fischer', 'Silva', 'Laurent', 'Braun', 'Marin'];
  const depts = ['Production', 'Supply chain', 'Sales', 'Logistics', 'Quality', 'Maintenance', 'Finance', 'People', 'Engineering', 'IT'];
  const out: SeedUser[] = [];
  for (let i = 0; i < 180; i++) {
    const f = first[Math.floor(r() * first.length)],
      l = last[Math.floor(r() * last.length)];
    const d = depts[Math.floor(r() * depts.length)];
    out.push({
      index: i,
      name: `${f} ${l}`,
      email: `${f}.${l}@${i % 5 === 0 ? 'auroravalves' : 'northwind'}.com`.toLowerCase(),
      dept: d,
      company: i % 5 === 0 ? 'Aurora Valves' : 'Northwind Industries',
    });
  }
  return out;
}

export interface SeedAgent {
  index: number;
  name: string;
  platform: string;
  domain: string;
  owner: string;
  reads: number;
  cost: number;
  on: boolean;
}

export function seedAgents(): SeedAgent[] {
  const r = seeded(11);
  const platforms = ['Microsoft Agent 365', 'Salesforce Agentforce', 'Databricks Genie', 'Snowflake Cortex', 'Amazon Bedrock', 'Google Cloud', 'Custom · Claude', 'ServiceNow', 'SAP Joule', 'Fabric IQ'];
  const roles = ['assistant', 'planner', 'copilot', 'analyst', 'monitor', 'router', 'summariser', 'forecaster', 'dispatcher', 'auditor'];
  const doms = ['Production', 'Supply chain', 'Sales', 'Logistics', 'Quality', 'Maintenance', 'Finance', 'People', 'Engineering'];
  const owners = ['Plant operations', 'Procurement', 'Commercial', 'Distribution', 'Quality assurance', 'Asset management', 'Controlling', 'Human resources', 'R&D'];
  const out: SeedAgent[] = [];
  for (let i = 0; i < 2400; i++) {
    const d = doms[Math.floor(r() * doms.length)],
      p = platforms[Math.floor(r() * platforms.length)];
    const reads = Math.floor(r() * r() * 9000);
    out.push({
      index: i,
      name: `${d.split(' ')[0]} ${roles[Math.floor(r() * roles.length)]} ${(i % 97) + 1}`,
      platform: p,
      domain: d,
      owner: owners[doms.indexOf(d)],
      reads,
      cost: Math.round(reads * (0.02 + r() * 0.12)),
      on: r() > 0.08,
    });
  }
  return out;
}

const ROLE_LABEL: Record<T.RoleName, string> = {
  owner: 'Owner',
  builder: 'Builder',
  governor: 'Governor',
  member: 'Member',
  administrator: 'Administrator',
  auditor: 'Auditor',
  agent: 'Agent',
};

const ROLE_TEXT: [T.RoleName, string][] = [
  ['owner', 'Owns one or more domain products. Approves and certifies changes in them.'],
  ['builder', 'Models, binds and connects. Proposes; cannot approve alone.'],
  ['governor', 'Second approver for certification, deletions and conflict resolutions.'],
  ['member', 'Reads the model, asks questions, comments. Can teach if enabled.'],
  ['administrator', 'This portal: settings, sources, companies, groups.'],
  ['auditor', 'Read-only, time-boxed access to the model and the audit log.'],
  ['agent', 'Machine identity. Reads the certified model through the gateway; every read is logged.'],
];

export const roleLabel = (r: T.RoleName): string => ROLE_LABEL[r];

interface MGroup {
  id: string;
  name: string;
  desc: string;
  members: number[];
  roles: T.RoleAssignment[];
}

interface MAgent extends SeedAgent {
  id: string;
}

export interface DirectoryHost {
  companies(): { id: string; name: string }[];
  addAudit(kind: string, what: string, ok: boolean): void;
  agentAccess(): boolean;
}

export class DirectoryRefusal extends Error {
  constructor(
    public status: number,
    public code: string,
    public detail: string,
  ) {
    super(detail);
  }
}

const pad = (n: number) => String(n).padStart(12, '0');

export interface ListArgs {
  page: number;
  pageSize: number;
  q: string;
  filter: Record<string, string>;
  sort: string | null;
  order: 'asc' | 'desc';
}

/** Parses the contract's list query (`page`, `pageSize`, `q`, `filter[field]`, `sort`, `order`). */
export function parseListArgs(search: string): ListArgs {
  const p = new URLSearchParams(search);
  const filter: Record<string, string> = {};
  for (const [k, v] of p.entries()) {
    const m = /^filter\[(.+)\]$/.exec(k);
    if (m) filter[m[1]] = v;
  }
  const size = Math.min(200, Math.max(1, Number(p.get('pageSize')) || 40));
  return {
    page: Math.max(1, Number(p.get('page')) || 1),
    pageSize: size,
    q: (p.get('q') || '').toLowerCase(),
    filter,
    sort: p.get('sort'),
    order: p.get('order') === 'desc' ? 'desc' : 'asc',
  };
}

/** One page of rows after search, filters and sort; rows keep their natural order unless sorted. */
export function pageOf<R>(
  rows: R[],
  args: ListArgs,
  fields: { search: (r: R) => string[]; filters: Record<string, (r: R) => string>; sorts: Record<string, (r: R) => string | number> },
): { items: R[]; page: number; pageSize: number; total: number } {
  for (const k of Object.keys(args.filter))
    if (!fields.filters[k]) throw new DirectoryRefusal(400, 'unknown_filter', `${k} is not a filter of this list`);
  if (args.sort && !fields.sorts[args.sort]) throw new DirectoryRefusal(400, 'unknown_sort', `${args.sort} is not a sort field of this list`);
  let list = rows.filter(
    (r) =>
      Object.entries(args.filter).every(([k, v]) => v.split(',').includes(fields.filters[k](r))) &&
      (!args.q || fields.search(r).some((s) => s.toLowerCase().includes(args.q))),
  );
  if (args.sort) {
    const key = fields.sorts[args.sort],
      dir = args.order === 'desc' ? -1 : 1;
    list = list.slice().sort((a, b) => {
      const x = key(a),
        y = key(b);
      return (x > y ? 1 : x < y ? -1 : 0) * dir;
    });
  }
  const start = (args.page - 1) * args.pageSize;
  return { items: list.slice(start, start + args.pageSize), page: args.page, pageSize: args.pageSize, total: list.length };
}

export function createDirectory(host: DirectoryHost) {
  const users = seedUsers();
  const userId = (i: number) => `00000000-0000-4000-a000-${pad(i + 1)}`;
  const userIndex = (id: string) => users.findIndex((u) => userId(u.index) === id);
  let groupSeq = 0,
    assignmentSeq = 0;
  const groupId = () => `00000000-0000-4000-b000-${pad(++groupSeq)}`;
  const assignmentId = () => `00000000-0000-4000-d000-${pad(++assignmentSeq)}`;

  function scopeOf(label: string): T.Scope {
    if (label === 'Tenant') return { kind: 'tenant', companyId: null, domainKey: null, label };
    const t = DOMAIN_TEMPLATES.find((x) => x.name === label);
    if (t) return { kind: 'domain', companyId: null, domainKey: t.key, label };
    const c = host.companies().find((x) => x.name === label);
    return { kind: 'company', companyId: c ? c.id : null, domainKey: null, label };
  }

  const assign = (gid: string, role: T.RoleName, scope: string): T.RoleAssignment => ({
    id: assignmentId(),
    groupId: gid,
    role,
    scope: scopeOf(scope),
  });

  function defaultGroups(): MGroup[] {
    const byDept = (d: string) => users.filter((u) => u.dept === d).map((u) => u.index);
    const g = (name: string, desc: string, members: number[], roles: [T.RoleName, string][]): MGroup => {
      const id = groupId();
      return { id, name, desc, members, roles: roles.map(([r, s]) => assign(id, r, s)) };
    };
    return [
      g('Plant operations · owners', 'Owns the Production domain product', byDept('Production').slice(0, 4), [['owner', 'Production']]),
      g('Procurement · builders', 'Models and binds Supply chain', byDept('Supply chain').slice(0, 6), [['builder', 'Supply chain']]),
      g('Commercial · owners', 'Owns Sales', byDept('Sales').slice(0, 3), [['owner', 'Sales']]),
      g(
        'Governance board',
        'Second approver for certification, deletions and conflicts',
        [...byDept('Quality').slice(0, 2), ...byDept('Finance').slice(0, 1), ...byDept('IT').slice(0, 1)],
        [['governor', 'Tenant']],
      ),
      g('Data platform team', 'Connects sources, administers the portal', byDept('IT').slice(0, 5), [
        ['administrator', 'Tenant'],
        ['builder', 'Tenant'],
      ]),
      g('All employees', 'Reads the model', users.map((u) => u.index), [['member', 'Tenant']]),
      g(
        'PE due-diligence team',
        'Time-boxed read access across the portfolio',
        users.filter((u) => u.dept === 'Finance').slice(0, 3).map((u) => u.index),
        [['auditor', 'Tenant']],
      ),
    ];
  }

  let groups = defaultGroups();
  const agents: MAgent[] = seedAgents().map((a) => ({ ...a, id: `00000000-0000-4000-c000-${pad(a.index + 1)}` }));
  const measured0 = agents.filter((a) => a.on).reduce((s, a) => s + a.cost, 0);
  const allocatedEur = Math.round((measured0 * 1.35) / 1000) * 1000 || 3000;

  const groupOf = (id: string) => {
    const g = groups.find((x) => x.id === id);
    if (!g) throw new DirectoryRefusal(404, 'group_not_found', 'group does not exist');
    return g;
  };

  const companyIdOf = (name: string) => host.companies().find((c) => c.name === name)?.id ?? null;

  const toUser = (u: SeedUser): T.User => {
    const mine = groups.filter((g) => g.members.includes(u.index));
    return {
      id: userId(u.index),
      name: u.name,
      email: u.email,
      department: u.dept,
      companyId: companyIdOf(u.company),
      companyName: u.company,
      groups: mine.map((g) => ({ id: g.id, name: g.name })),
      effectiveRoles: mine.flatMap((g) => g.roles),
      lastLoginAt: null,
    };
  };

  const toGroup = (g: MGroup, withMembers = false): T.Group => ({
    id: g.id,
    name: g.name,
    description: g.desc,
    validUntil: null,
    memberCount: g.members.length,
    members: withMembers ? g.members.map((i) => toUser(users[i])) : undefined,
    roles: g.roles.map((r) => ({ ...r })),
  });

  const toAgent = (a: MAgent): T.Agent => {
    const t = DOMAIN_TEMPLATES.find((x) => x.name === a.domain);
    return {
      id: a.id,
      name: a.name,
      platform: a.platform,
      companyId: null,
      domainKey: t ? t.key : null,
      domainName: a.domain,
      owner: a.owner,
      access: a.on,
      reads: a.reads,
      costEur: a.cost,
    };
  };

  const cleanName = (v: unknown, max: number, field: string): string => {
    const s = typeof v === 'string' ? v.trim() : '';
    if (!s) throw new DirectoryRefusal(422, 'validation_failed', `${field} is required`);
    if (s.length > max) throw new DirectoryRefusal(422, 'validation_failed', `${field} is longer than ${max} characters`);
    return s;
  };

  return {
    listUsers(search: string) {
      return pageOf(users.map(toUser), parseListArgs(search), {
        search: (u) => [u.name, u.email, u.department || '', u.companyName || '', ...u.groups.map((g) => g.name), ...u.effectiveRoles.map((r) => ROLE_LABEL[r.role])],
        filters: {
          companyId: (u) => u.companyId || '',
          department: (u) => u.department || '',
          inGroup: (u) => String(u.groups.length > 0),
        },
        sorts: { name: (u) => u.name, email: (u) => u.email, department: (u) => u.department || '', company: (u) => u.companyName || '' },
      });
    },
    getUser(id: string) {
      const i = userIndex(id);
      if (i < 0) throw new DirectoryRefusal(404, 'user_not_found', 'user does not exist');
      return toUser(users[i]);
    },
    listGroups(search: string) {
      return pageOf(groups.map((g) => toGroup(g)), parseListArgs(search), {
        search: (g) => [g.name, g.description, ...g.roles.map((r) => `${ROLE_LABEL[r.role]} · ${r.scope.label}`)],
        filters: {},
        sorts: { name: (g) => g.name, members: (g) => g.memberCount },
      });
    },
    getGroup(id: string) {
      return toGroup(groupOf(id), true);
    },
    createGroup(body: T.GroupInput) {
      const name = cleanName(body?.name, 120, 'name');
      if (groups.some((g) => g.name === name)) throw new DirectoryRefusal(409, 'duplicate_group', `${name} already exists`);
      const g: MGroup = { id: groupId(), name, desc: (body.description || '').trim().slice(0, 300), members: [], roles: [] };
      groups.push(g);
      host.addAudit('groups', `${name} created`, true);
      return toGroup(g);
    },
    updateGroup(id: string, body: T.GroupInput) {
      const g = groupOf(id);
      const name = cleanName(body?.name, 120, 'name');
      if (groups.some((x) => x !== g && x.name === name)) throw new DirectoryRefusal(409, 'duplicate_group', `${name} already exists`);
      g.name = name;
      g.desc = (body.description || '').trim().slice(0, 300);
      host.addAudit('groups', `${name} edited`, true);
      return toGroup(g);
    },
    deleteGroup(id: string) {
      const g = groupOf(id);
      groups = groups.filter((x) => x !== g);
      host.addAudit('groups', `${g.name} deleted`, true);
    },
    setMember(gid: string, uid: string, on: boolean) {
      const g = groupOf(gid);
      const i = userIndex(uid);
      if (i < 0) throw new DirectoryRefusal(404, 'user_not_found', 'user does not exist');
      const has = g.members.includes(i);
      if (on && !has) g.members.push(i);
      if (!on && has) g.members = g.members.filter((x) => x !== i);
      if (on !== has) host.addAudit('groups', `${users[i].name} ${on ? 'added to' : 'removed from'} ${g.name}`, true);
    },
    addRole(gid: string, body: { role: T.RoleName; scope: T.Scope }) {
      const g = groupOf(gid);
      if (!body || !ROLE_LABEL[body.role] || body.role === 'agent') throw new DirectoryRefusal(422, 'validation_failed', 'unknown role');
      const label = body.scope?.label;
      if (!label || !this.listScopes().some((s) => s.label === label && s.kind === body.scope.kind))
        throw new DirectoryRefusal(422, 'validation_failed', 'unknown scope');
      if (body.scope.kind === 'domain' && body.scope.companyId) throw new DirectoryRefusal(422, 'validation_failed', 'a domain scope takes no company');
      if (body.role === 'administrator' && body.scope.kind !== 'tenant')
        throw new DirectoryRefusal(422, 'administrator_scope', 'Administrator only applies at Tenant scope');
      if (g.roles.some((r) => r.role === body.role && r.scope.label === label))
        throw new DirectoryRefusal(409, 'duplicate_role', `${g.name} already holds ${ROLE_LABEL[body.role]} · ${label}`);
      const a = assign(g.id, body.role, label);
      g.roles.push(a);
      host.addAudit('roles', `${ROLE_LABEL[body.role]} · ${label} given to ${g.name}`, true);
      return a;
    },
    removeRole(gid: string, aid: string) {
      const g = groupOf(gid);
      const a = g.roles.find((r) => r.id === aid);
      if (!a) throw new DirectoryRefusal(404, 'assignment_not_found', 'role assignment does not exist');
      g.roles = g.roles.filter((r) => r !== a);
      host.addAudit('roles', `${ROLE_LABEL[a.role]} removed from ${g.name}`, true);
    },
    listRoles(): T.RoleInfo[] {
      const holders = (role: T.RoleName) => new Set(groups.filter((g) => g.roles.some((r) => r.role === role)).flatMap((g) => g.members)).size;
      return ROLE_TEXT.map(([role, description]) => ({
        role,
        label: ROLE_LABEL[role],
        description,
        assigned: role === 'agent' ? (host.agentAccess() ? agents.filter((a) => a.on).length : 0) : holders(role),
      }));
    },
    listRoleGroups(role: string): T.RoleGroup[] {
      if (!ROLE_LABEL[role as T.RoleName]) throw new DirectoryRefusal(404, 'role_not_found', 'role does not exist');
      return groups.map((g) => ({ group: toGroup(g), scopes: g.roles.filter((r) => r.role === role).map((r) => r.scope) }));
    },
    listScopes(): T.Scope[] {
      return [
        { kind: 'tenant', companyId: null, domainKey: null, label: 'Tenant' },
        ...host.companies().map((c) => ({ kind: 'company' as const, companyId: c.id, domainKey: null, label: c.name })),
        ...DOMAIN_TEMPLATES.map((t) => ({ kind: 'domain' as const, companyId: null, domainKey: t.key, label: t.name })),
      ];
    },
    listAgents(search: string) {
      return pageOf(agents.map(toAgent), parseListArgs(search), {
        search: (a) => [a.name, a.platform, a.domainName || '', a.owner],
        filters: { platform: (a) => a.platform, domainKey: (a) => a.domainKey || '', access: (a) => String(a.access) },
        sorts: { name: (a) => a.name, platform: (a) => a.platform, domain: (a) => a.domainName || '', owner: (a) => a.owner, reads: (a) => a.reads, cost: (a) => a.costEur },
      });
    },
    updateAgent(id: string, body: { access?: unknown }) {
      const a = agents.find((x) => x.id === id);
      if (!a) throw new DirectoryRefusal(404, 'agent_not_found', 'agent does not exist');
      if (typeof body?.access !== 'boolean') throw new DirectoryRefusal(422, 'validation_failed', 'access is required');
      if (a.on !== body.access) {
        a.on = body.access;
        host.addAudit('agents', `${a.name} ${a.on ? 'enabled' : 'disabled'}`, true);
      }
      return toAgent(a);
    },
    cost(month: string): T.CostSummary {
      const on = agents.filter((a) => a.on);
      const measured = on.reduce((s, a) => s + a.cost, 0),
        reads = on.reduce((s, a) => s + a.reads, 0);
      const byP = new Map<string, { n: number; cost: number }>();
      for (const a of on) {
        const v = byP.get(a.platform) || { n: 0, cost: 0 };
        v.n++;
        v.cost += a.cost;
        byP.set(a.platform, v);
      }
      return {
        month,
        measuredEur: measured,
        allocatedEur,
        agentsRegistered: agents.length,
        agentsWithAccess: on.length,
        reads,
        byPlatform: [...byP.entries()]
          .sort((a, b) => b[1].cost - a[1].cost)
          .map(([platform, v]) => ({ platform, agentsWithAccess: v.n, costEur: v.cost, sharePercent: Math.round((v.cost / measured) * 100) })),
      };
    },
  };
}

export type Directory = ReturnType<typeof createDirectory>;
