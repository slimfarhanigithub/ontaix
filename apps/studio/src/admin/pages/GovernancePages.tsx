/**
 * The Governance group of the admin portal: Groups, Users, Roles, Audit log and Cost management
 * (`pageGroups` to `pageAgents`, reference lines 1017-1036). Directory, audit and cost data come
 * from the API; an unavailable endpoint leaves the page empty.
 */
import { useEffect, useState } from 'react';

import { api } from '../../api/client';
import type { CostSummary, Group, RoleInfo } from '../../api/types';
import { useStore } from '../../shell/dom';
import { directory, failed } from '../adminData';
import { agentRegistry, deleteGroupDialog, groupEdit, groupMembers, groupRoles, roleGroups } from '../actions';
import { List, type Column } from '../List';
import { en } from '../listModel';
import { distinctRoles, roleLabel } from '../roles';
import { SetRow } from '../Toggle';
import { RowActions } from '../RowActions';

const ACT = (w: number) => ({ width: `${w}px`, textAlign: 'center' as const });

interface GroupRow extends Record<string, unknown> {
  id: string;
  g: Group;
  name: string;
  desc: string;
  members: number;
  roles: string;
  nroles: number;
}

export function Groups() {
  const st = useStore();
  const rows: GroupRow[] = directory.groups.map((g) => ({
    id: g.id,
    g,
    name: g.name,
    desc: g.description,
    members: g.memberCount,
    roles: g.roles.map((r) => `${roleLabel(r.role)} · ${r.scope.label}`).join(', ') || '—',
    nroles: g.roles.length,
  }));
  const columns: Column[] = [
    { label: 'Group', key: 'name' },
    { label: 'Description', key: 'desc' },
    { label: 'Members', key: 'members', num: true },
    { label: 'Roles', key: 'roles' },
    { label: '', w: '300px' },
  ];
  return (
    <>
      <h2>Groups</h2>
      <p className="lead">
        Groups are Ontaix’s own: you create them here, add users, and give each group roles with a scope. Nothing depends on your identity provider’s
        groups; sign-in can still come from anywhere.
      </p>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
        <button className="btn primary" data-act="newGroup" onClick={() => groupEdit(null)}>
          + Create a group
        </button>
      </div>
      <div className="lst-host" id="lstGroups" style={{ height: 'calc(100% - 120px)' }}>
        {directory.loaded ? (
        <List
          key={st.ui.adminRev}
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          searchKeys={['name', 'desc', 'roles']}
          pageSize={40}
          renderRow={(r) => (
            <>
              <td>
                <b>{r.name}</b>
              </td>
              <td style={{ color: 'var(--ink-2)' }}>{r.desc}</td>
              <td className="num">{r.members}</td>
              <td>{r.roles}</td>
              <td className="act">
                <RowActions
                  id={`grp-${r.g.id}`}
                  primary={
                    <button data-fn="members" style={ACT(78)} onClick={() => groupMembers(r.g)}>
                      Members
                    </button>
                  }
                  items={[
                    { label: 'Roles', icon: 'key', group: 1, attrs: { 'data-fn': 'roles' }, act: () => groupRoles(r.g) },
                    { label: 'Edit', icon: 'edit', group: 1, attrs: { 'data-fn': 'edit' }, act: () => groupEdit(r.g) },
                    { label: 'Delete', icon: 'delete', group: 2, danger: true, attrs: { 'data-fn': 'del' }, act: () => deleteGroupDialog(r.g) },
                  ]}
                />
              </td>
            </>
          )}
          footer={(l) => `${l.reduce((a, r) => a + r.members, 0)} memberships`}
        />
        ) : null}
      </div>
    </>
  );
}

interface UserRow extends Record<string, unknown> {
  id: string;
  name: string;
  email: string;
  dept: string;
  company: string;
  groups: string;
  roles: string;
}

export function Users() {
  const st = useStore();
  const rows: UserRow[] = directory.users.map((u) => ({
    id: u.id,
    name: u.name,
    email: u.email,
    dept: u.department || '',
    company: u.companyName || '',
    groups: u.groups.map((g) => g.name).join(', ') || '—',
    roles: distinctRoles(u.effectiveRoles).join(', ') || '—',
  }));
  const columns: Column[] = [
    { label: 'User', key: 'name' },
    { label: 'Email', key: 'email' },
    { label: 'Department', key: 'dept' },
    { label: 'Company', key: 'company' },
    { label: 'Groups', key: 'groups' },
    { label: 'Effective roles', key: 'roles' },
  ];
  return (
    <>
      <h2>Users</h2>
      <p className="lead">Everyone who can sign in. Roles come from the groups a user belongs to; a user with no group can read nothing.</p>
      <div className="lst-host" id="lstUsers" style={{ height: 'calc(100% - 80px)' }}>
        {directory.loaded ? (
        <List
          key={st.ui.adminRev}
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          searchKeys={['name', 'email', 'dept', 'company', 'groups', 'roles']}
          filterKey="company"
          pageSize={40}
          renderRow={(r) => (
            <>
              <td>
                <b>{r.name}</b>
              </td>
              <td className="wrap" style={{ color: 'var(--ink-2)' }}>{r.email}</td>
              <td>{r.dept}</td>
              <td>{r.company}</td>
              <td>{r.groups}</td>
              <td>{r.roles}</td>
            </>
          )}
          footer={(l) => `${l.filter((r) => r.groups !== '—').length} in at least one group`}
        />
        ) : null}
      </div>
    </>
  );
}

/** Loads one API resource each time the portal renders from scratch; a failure leaves it null. `load` must be stable. */
function useAdminResource<T>(load: () => Promise<T>): T | null {
  const st = useStore();
  const [value, setValue] = useState<T | null>(null);
  const rev = st.ui.adminRev;
  useEffect(() => {
    let live = true;
    load().then(
      (v) => {
        if (live) setValue(v);
      },
      (err: unknown) => failed(err, 'Unavailable'),
    );
    return () => {
      live = false;
    };
  }, [rev, load]);
  return value;
}

const loadRoles = () => api.listRoles();
const loadCost = () => api.getCost();

export function Roles() {
  const roles: RoleInfo[] = useAdminResource(loadRoles) || [];
  const people = roles.filter((r) => r.role !== 'agent');
  const agent = roles.find((r) => r.role === 'agent');
  return (
    <>
      <h2>Roles</h2>
      <p className="lead">
        Five people roles plus Auditor and Agent. A role is given to a group, with a scope: Tenant, a company, or a domain product. The count is the
        number of users who hold it through their groups.
      </p>
      <table className="tbl">
        <thead>
          <tr>
            <th>Role</th>
            <th>What it can do</th>
            <th>Assigned</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {people.map((r) => (
            <tr key={r.role}>
              <td>
                <b>{r.label}</b>
              </td>
              <td>{r.description}</td>
              <td>{r.assigned}</td>
              <td className="act">
                <button data-act="groups" data-id={r.label} style={ACT(120)} onClick={() => roleGroups(r.label)}>
                  Groups
                </button>
              </td>
            </tr>
          ))}
          {agent ? (
            <tr>
              <td>
                <b>{agent.label}</b>
              </td>
              <td>{agent.description}</td>
              <td>{en(agent.assigned)}</td>
              <td className="act">
                <button data-act="registry" style={ACT(120)} onClick={agentRegistry}>
                  Registry
                </button>
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </>
  );
}

export function AuditLog() {
  useStore();
  const rows = directory.audit;
  return (
    <>
      <h2>Audit log</h2>
      <p className="lead">Every approval, rejection, setting change and connection, append-only.</p>
      <div className="log">
        {rows.length ? (
          rows.map((e) => (
            <div key={e.id}>
              <span>{new Date(e.at).toLocaleTimeString('en-GB')}</span>
              <span>{e.kind}</span>
              <span>{e.actor.platformAccountId ? `${e.what} · platform super admin` : e.what}</span>
              <span className={e.ok ? 'ok' : 'no'}>{e.ok ? 'approved' : 'rejected'}</span>
            </div>
          ))
        ) : (
          <div>
            <span></span>
            <span></span>
            <span style={{ color: 'var(--ink-3)' }}>Nothing yet.</span>
            <span></span>
          </div>
        )}
      </div>
    </>
  );
}

export function CostManagement() {
  const cost: CostSummary | null = useAdminResource(loadCost);
  const measured = cost ? cost.measuredEur : 0;
  return (
    <>
      <h2>Cost management</h2>
      <p className="lead">
        Agents from any platform that read this model through the gateway, and what they cost this month, measured against what was allocated.
      </p>
      <div className="kpis">
        <div>
          <b>{`€ ${en(measured)}`}</b>
          <span>measured this month</span>
        </div>
        <div>
          <b>{`€ ${cost ? cost.allocatedEur : 0}`}</b>
          <span>allocated</span>
        </div>
        <div>
          <b>{en(cost ? cost.agentsRegistered : 0)}</b>
          <span>{`agents registered · ${en(cost ? cost.agentsWithAccess : 0)} with access`}</span>
        </div>
        <div>
          <b>{en(cost ? cost.reads : 0)}</b>
          <span>model reads</span>
        </div>
      </div>
      <SetRow k="agentAccess" title="Agents may read the certified model" desc="When off, the gateway answers nothing." />
      <SetRow k="costCap" title="Stop agents at 100 percent of allocation" desc="Alerts at 50 and 80 percent." />
      <h3>By platform</h3>
      <table className="tbl">
        <thead>
          <tr>
            <th>Platform</th>
            <th className="num">Agents with access</th>
            <th className="num">Cost · month</th>
            <th className="num">Share</th>
          </tr>
        </thead>
        <tbody>
          {(cost ? cost.byPlatform : []).map((p) => (
            <tr key={p.platform}>
              <td>
                <b>{p.platform}</b>
              </td>
              <td className="num">{en(p.agentsWithAccess)}</td>
              <td className="num">{`€ ${en(p.costEur)}`}</td>
              <td className="num">{`${p.sharePercent} %`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: '12px' }}>
        <button className="btn primary" data-act="registry" onClick={agentRegistry}>
          Open the agent registry
        </button>
      </div>
    </>
  );
}
