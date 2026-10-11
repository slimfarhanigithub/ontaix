/**
 * `Users of <organization>`: the organization's accounts in the reference's list dialog, with
 * `+ Add a user` and the row actions Edit, Reset password and Disable or Enable, and the
 * dialogs behind them. Passwords typed here live in component state only until the call
 * answers, and are cleared after every submit.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { confirmDialog } from '../admin/actions';
import { attempt, failed, fetchAll } from '../admin/adminData';
import { List, type Column } from '../admin/List';
import { api } from '../api/client';
import type { Group, Organization, OrganizationUser } from '../api/types';
import { DialogFrame } from '../shell/Dialog';
import { store } from '../store/store';
import { PlatformDialog } from './PlatformDialog';
import { RowActions } from '../admin/RowActions';

const ACT = (w: number) => ({ width: `${w}px`, textAlign: 'center' as const });

export const ADD_USER_NOTE = 'They must choose a new password at first sign-in. Give them this password yourself; Ontology Builder never shows it again.';
export const RESET_NOTE = 'They must choose a new password at next sign-in, and every session of theirs is signed out.';

export type UserStatus = 'Active' | 'Disabled' | 'Locked' | 'Must change password';

export function userStatus(u: Pick<OrganizationUser, 'status' | 'locked' | 'mustChangePassword'>): UserStatus {
  if (u.status === 'disabled') return 'Disabled';
  if (u.locked) return 'Locked';
  if (u.mustChangePassword) return 'Must change password';
  return 'Active';
}

interface UserRow extends Record<string, unknown> {
  id: string;
  u: OrganizationUser;
  name: string;
  email: string;
  groups: string;
  status: UserStatus;
}

export function usersDialog(org: Organization, changed: () => void): void {
  store.openDialog({ render: (close) => <UsersDialog org={org} close={close} changed={changed} /> });
}

function UsersDialog({ org, close, changed }: { org: Organization; close: () => void; changed: () => void }) {
  const [users, setUsers] = useState<OrganizationUser[] | null>(null);
  const [rev, setRev] = useState(0);
  const back = useRef<HTMLDivElement>(null);
  const refresh = useCallback(() => {
    setRev((r) => r + 1);
    changed();
  }, [changed]);
  useEffect(() => {
    let live = true;
    fetchAll((p) => api.listOrganizationUsers(org.id, p)).then(
      (items) => {
        if (live) setUsers(items);
      },
      (err: unknown) => {
        failed(err, 'Unavailable');
        if (live) setUsers([]);
      },
    );
    return () => {
      live = false;
    };
  }, [org.id, rev]);
  useEffect(() => {
    const t = setTimeout(() => back.current?.querySelector<HTMLInputElement>('.search')?.focus(), 40);
    return () => clearTimeout(t);
  }, []);
  const rows: UserRow[] = (users || []).map((u) => ({
    id: u.id,
    u,
    name: u.name,
    email: u.email,
    groups: u.groups.map((g) => g.name).join(', ') || '—',
    status: userStatus(u),
  }));
  const columns: Column[] = [
    { label: 'Name', key: 'name' },
    { label: 'Email', key: 'email' },
    { label: 'Groups', key: 'groups' },
    { label: 'Status', key: 'status' },
    // Three buttons (40, 96 and 56 wide plus 22 of padding and border each), two 6px gaps and the
    // cell padding: 290px.
    { label: '', w: '290px' },
  ];
  return (
    <DialogFrame
      title={`Users of ${org.name}`}
      large
      onClose={close}
      backRef={back}
      footer={
        <button className="btn primary" data-i="0" onClick={() => addUserDialog(org, refresh)}>
          + Add a user
        </button>
      }
    >
      <div className="lst-host">
        {users ? (
          <List
            key={rev}
            columns={columns}
            rows={rows}
            rowKey={(r) => r.id}
            searchKeys={['name', 'email', 'groups', 'status']}
            filterKey="status"
            pageSize={40}
            renderRow={(r) => (
              <>
                <td>
                  <b>{r.name}</b>
                </td>
                <td className="wrap" style={{ color: 'var(--ink-2)' }}>{r.email}</td>
                <td>{r.groups}</td>
                <td>
                  <span className={`st${r.status === 'Disabled' ? ' off' : r.status === 'Active' ? '' : ' pend'}`}>
                    <i></i>
                    {r.status}
                  </span>
                </td>
                <td className="act">
                  <RowActions
                    id={`usr-${r.u.id}`}
                    primary={
                      <button data-fn="edit" style={ACT(40)} onClick={() => editUserDialog(org, r.u, refresh)}>
                        Edit
                      </button>
                    }
                    items={[
                      { label: 'Reset password', icon: 'key', group: 1, attrs: { 'data-fn': 'reset' }, act: () => resetPasswordDialog(org, r.u, refresh) },
                      r.u.status === 'disabled'
                        ? { label: 'Enable', icon: 'power', group: 2, attrs: { 'data-fn': 'enable' }, act: () => void enableUser(org, r.u, refresh) }
                        : { label: 'Disable', icon: 'power', group: 2, danger: true, attrs: { 'data-fn': 'disable' }, act: () => disableUserDialog(org, r.u, refresh) },
                    ]}
                  />
                </td>
              </>
            )}
            footer={(l) => `${l.filter((r) => r.status === 'Active').length} active`}
          />
        ) : null}
      </div>
    </DialogFrame>
  );
}

/** The organization's groups as checkboxes, in the reference's `.chk` rows. */
function GroupChecks({ orgId, selected, onChange }: { orgId: string; selected: string[]; onChange: (ids: string[]) => void }) {
  const [groups, setGroups] = useState<Group[]>([]);
  useEffect(() => {
    let live = true;
    api.listOrganizationGroups(orgId).then(
      (gs) => {
        if (live) setGroups(gs);
      },
      (err: unknown) => failed(err, 'Unavailable'),
    );
    return () => {
      live = false;
    };
  }, [orgId]);
  const toggle = (id: string, on: boolean) => onChange(on ? [...selected, id] : selected.filter((x) => x !== id));
  return (
    <>
      <label>Groups</label>
      <div style={{ display: 'grid', gap: '6px' }}>
        {groups.map((g) => (
          <label className="chk" key={g.id}>
            <input type="checkbox" checked={selected.includes(g.id)} onChange={(e) => toggle(g.id, e.target.checked)} />
            <span>
              <b>{g.name}</b>
              <small>{g.description}</small>
            </span>
          </label>
        ))}
      </div>
    </>
  );
}

export function addUserDialog(org: Organization, done: () => void): void {
  store.openDialog({ render: (close) => <AddUser org={org} close={close} done={done} /> });
}

function AddUser({ org, close, done }: { org: Organization; close: () => void; done: () => void }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [department, setDepartment] = useState('');
  const [password, setPassword] = useState('');
  const [groupIds, setGroupIds] = useState<string[]>([]);
  return (
    <PlatformDialog
      title="Add a user"
      close={close}
      label="Add user"
      note={ADD_USER_NOTE}
      onRefused={() => setPassword('')}
      onSave={() =>
        api
          .createOrganizationUser(org.id, {
            name: name.trim(),
            email: email.trim(),
            department: department.trim() || null,
            password,
            groupIds,
          })
          .then((u) => {
            setPassword('');
            store.toast2('Added', u.name);
            done();
          })
      }
    >
      <label htmlFor="auName">Name</label>
      <input id="auName" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
      <label htmlFor="auEmail">Email</label>
      <input id="auEmail" type="email" autoComplete="off" value={email} maxLength={254} onChange={(e) => setEmail(e.target.value)} />
      <label htmlFor="auDept">Department (optional)</label>
      <input id="auDept" value={department} maxLength={120} onChange={(e) => setDepartment(e.target.value)} />
      <label htmlFor="auPassword">Initial password</label>
      <input id="auPassword" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <GroupChecks orgId={org.id} selected={groupIds} onChange={setGroupIds} />
    </PlatformDialog>
  );
}

export function editUserDialog(org: Organization, u: OrganizationUser, done: () => void): void {
  store.openDialog({ render: (close) => <EditUser org={org} u={u} close={close} done={done} /> });
}

function EditUser({ org, u, close, done }: { org: Organization; u: OrganizationUser; close: () => void; done: () => void }) {
  const [name, setName] = useState(u.name);
  const [department, setDepartment] = useState(u.department || '');
  const [groupIds, setGroupIds] = useState<string[]>(u.groups.map((g) => g.id));
  return (
    <PlatformDialog
      title={`Edit ${u.name}`}
      sub={u.email}
      close={close}
      label="Save"
      onSave={() =>
        api.updateOrganizationUser(org.id, u.id, { name: name.trim(), department: department.trim() || null, groupIds }).then((next) => {
          store.toast2('Saved', next.name);
          done();
        })
      }
    >
      <label htmlFor="euName">Name</label>
      <input id="euName" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
      <label htmlFor="euDept">Department (optional)</label>
      <input id="euDept" value={department} maxLength={120} onChange={(e) => setDepartment(e.target.value)} />
      <GroupChecks orgId={org.id} selected={groupIds} onChange={setGroupIds} />
    </PlatformDialog>
  );
}

export function resetPasswordDialog(org: Organization, u: OrganizationUser, done: () => void): void {
  store.openDialog({ render: (close) => <ResetPassword org={org} u={u} close={close} done={done} /> });
}

function ResetPassword({ org, u, close, done }: { org: Organization; u: OrganizationUser; close: () => void; done: () => void }) {
  const [password, setPassword] = useState('');
  return (
    <PlatformDialog
      title={`Reset password for ${u.name}`}
      close={close}
      label="Reset password"
      note={RESET_NOTE}
      onRefused={() => setPassword('')}
      onSave={() =>
        api.resetOrganizationUserPassword(org.id, u.id, password).then(() => {
          setPassword('');
          store.toast2('Password reset', u.name);
          done();
        })
      }
    >
      <label htmlFor="rpPassword">New password</label>
      <input id="rpPassword" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
    </PlatformDialog>
  );
}

/** `Disable <name>?` in the reference's `confirmDialog` with a `danger` button. */
export function disableUserDialog(org: Organization, u: OrganizationUser, done: () => void): void {
  confirmDialog(
    `Disable ${u.name}?`,
    'They are signed out and can no longer sign in.',
    'Disable',
    () =>
      attempt(() => api.disableOrganizationUser(org.id, u.id)).then((res) => {
        if (!res) return;
        store.toast2('Disabled', u.name);
        done();
      }),
    true,
  );
}

export function enableUser(org: Organization, u: OrganizationUser, done: () => void): Promise<void> {
  return attempt(() => api.enableOrganizationUser(org.id, u.id)).then((res) => {
    if (!res) return;
    store.toast2('Enabled', u.name);
    done();
  });
}
