/**
 * `Users of <organization>`: the organization's accounts in the reference's list dialog, with
 * `+ Add a user`, `Add existing account`, the row actions Edit, Reset password, Disable or
 * Enable and Remove from organization, and the dialogs behind them. Passwords typed here live
 * in component state only until the call answers, and are cleared after every submit.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { confirmDialog } from '../admin/actions';
import { attempt, failed, fetchAll } from '../admin/adminData';
import { List, type Column } from '../admin/List';
import { api } from '../api/client';
import { ApiError, type Group, type Organization, type OrganizationUser } from '../api/types';
import { t, useT } from '../i18n/i18n';
import { DialogFrame } from '../shell/Dialog';
import { store } from '../store/store';
import { PlatformDialog } from './PlatformDialog';
import { RowActions } from '../admin/RowActions';

const ACT = (w: number) => ({ width: `${w}px`, textAlign: 'center' as const });

export const addUserNote = (): string => t('platform.user.addNote');
export const emailTaken = (): string => t('platform.user.emailTaken');
export const addExistingNote = (): string => t('platform.user.addExistingNote');
export const resetNote = (): string => t('platform.user.resetNote');

export type UserStatus = 'active' | 'disabled' | 'locked' | 'mustChangePassword';

export function userStatus(u: Pick<OrganizationUser, 'status' | 'locked' | 'mustChangePassword'>): UserStatus {
  if (u.status === 'disabled') return 'disabled';
  if (u.locked) return 'locked';
  if (u.mustChangePassword) return 'mustChangePassword';
  return 'active';
}

/** The status as the list shows it: `Active`, `Disabled`, `Locked` or `Must change password`. */
export const userStatusText = (status: UserStatus): string => t(`platform.users.status.${status}`);

interface UserRow extends Record<string, unknown> {
  id: string;
  u: OrganizationUser;
  name: string;
  email: string;
  groups: string;
  statusCode: UserStatus;
  /** The status text in the portal language; the filter pills and the search read it. */
  status: string;
}

export function usersDialog(org: Organization, changed: () => void): void {
  store.openDialog({ render: (close) => <UsersDialog org={org} close={close} changed={changed} /> });
}

function UsersDialog({ org, close, changed }: { org: Organization; close: () => void; changed: () => void }) {
  const t = useT();
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
        failed(err, t('common.lead.unavailable'));
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
    statusCode: userStatus(u),
    status: userStatusText(userStatus(u)),
  }));
  const columns: Column[] = [
    { label: t('platform.users.column.name'), key: 'name' },
    { label: t('platform.users.column.email'), key: 'email' },
    { label: t('platform.users.column.groups'), key: 'groups' },
    { label: t('platform.users.column.status'), key: 'status' },
    // Three buttons (40, 96 and 56 wide plus 22 of padding and border each), two 6px gaps and the
    // cell padding: 290px.
    { label: '', w: '290px' },
  ];
  return (
    <DialogFrame
      title={t('platform.users.title', { organization: org.name })}
      large
      onClose={close}
      backRef={back}
      footer={
        <>
          <button className="btn primary" data-i="0" onClick={() => addUserDialog(org, refresh)}>
            {t('platform.users.addUser')}
          </button>
          <button className="btn" data-i="1" data-act="addExisting" onClick={() => addExistingAccountDialog(org, refresh)}>
            {t('platform.users.addExisting')}
          </button>
        </>
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
                  <span className={`st${r.statusCode === 'disabled' ? ' off' : r.statusCode === 'active' ? '' : ' pend'}`}>
                    <i></i>
                    {r.status}
                  </span>
                </td>
                <td className="act">
                  <RowActions
                    id={`usr-${r.u.id}`}
                    primary={
                      <button data-fn="edit" style={ACT(40)} onClick={() => editUserDialog(org, r.u, refresh)}>
                        {t('common.edit')}
                      </button>
                    }
                    items={[
                      { label: t('platform.users.resetPassword'), icon: 'key', group: 1, attrs: { 'data-fn': 'reset' }, act: () => resetPasswordDialog(org, r.u, refresh) },
                      r.u.status === 'disabled'
                        ? { label: t('common.enable'), icon: 'power', group: 2, attrs: { 'data-fn': 'enable' }, act: () => void enableUser(org, r.u, refresh) }
                        : { label: t('common.disable'), icon: 'power', group: 2, danger: true, attrs: { 'data-fn': 'disable' }, act: () => disableUserDialog(org, r.u, refresh) },
                      { label: t('platform.users.remove'), icon: 'delete', group: 3, danger: true, attrs: { 'data-fn': 'remove' }, act: () => removeUserDialog(org, r.u, refresh) },
                    ]}
                  />
                </td>
              </>
            )}
            footer={(l) => t('platform.users.footer', { n: l.filter((r) => r.statusCode === 'active').length })}
          />
        ) : null}
      </div>
    </DialogFrame>
  );
}

/** The organization's groups as checkboxes, in the reference's `.chk` rows. */
function GroupChecks({ orgId, selected, onChange }: { orgId: string; selected: string[]; onChange: (ids: string[]) => void }) {
  const t = useT();
  const [groups, setGroups] = useState<Group[]>([]);
  useEffect(() => {
    let live = true;
    api.listOrganizationGroups(orgId).then(
      (gs) => {
        if (live) setGroups(gs);
      },
      (err: unknown) => failed(err, t('common.lead.unavailable')),
    );
    return () => {
      live = false;
    };
  }, [orgId]);
  const toggle = (id: string, on: boolean) => onChange(on ? [...selected, id] : selected.filter((x) => x !== id));
  return (
    <>
      <label>{t('platform.user.groups')}</label>
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
  const t = useT();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [department, setDepartment] = useState('');
  const [password, setPassword] = useState('');
  const [groupIds, setGroupIds] = useState<string[]>([]);
  return (
    <PlatformDialog
      title={t('platform.user.addTitle')}
      close={close}
      label={t('platform.user.add')}
      note={addUserNote()}
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
          .then(
            (u) => {
              setPassword('');
              store.toast2(t('platform.user.added'), u.name);
              done();
            },
            (err: unknown) => {
              // An email that already has an account is added through Add existing account instead.
              if (err instanceof ApiError && err.problem.code === 'email_taken') throw new ApiError(err.status, { ...err.problem, detail: emailTaken() });
              throw err;
            },
          )
      }
    >
      <label htmlFor="auName">{t('platform.user.name')}</label>
      <input id="auName" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
      <label htmlFor="auEmail">{t('platform.user.email')}</label>
      <input id="auEmail" type="email" autoComplete="off" value={email} maxLength={254} onChange={(e) => setEmail(e.target.value)} />
      <label htmlFor="auDept">{t('platform.user.department')}</label>
      <input id="auDept" value={department} maxLength={120} onChange={(e) => setDepartment(e.target.value)} />
      <label htmlFor="auPassword">{t('platform.user.initialPassword')}</label>
      <input id="auPassword" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <GroupChecks orgId={org.id} selected={groupIds} onChange={setGroupIds} />
    </PlatformDialog>
  );
}

export function addExistingAccountDialog(org: Organization, done: () => void): void {
  store.openDialog({ render: (close) => <AddExistingAccount org={org} close={close} done={done} /> });
}

/** An account of another organization joins this one: its email and the groups it takes here. */
function AddExistingAccount({ org, close, done }: { org: Organization; close: () => void; done: () => void }) {
  const t = useT();
  const [email, setEmail] = useState('');
  const [groupIds, setGroupIds] = useState<string[]>([]);
  return (
    <PlatformDialog
      title={t('platform.user.addExistingTitle')}
      sub={t('platform.user.addExistingSub', { organization: org.name })}
      close={close}
      label={t('platform.user.addAccount')}
      note={addExistingNote()}
      onSave={() =>
        api.addOrganizationMembership(org.id, { email: email.trim(), groupIds }).then((u) => {
          store.toast2(t('platform.user.added'), u.name);
          done();
        })
      }
    >
      <label htmlFor="aeEmail">{t('platform.user.email')}</label>
      <input id="aeEmail" type="email" autoComplete="off" value={email} maxLength={254} onChange={(e) => setEmail(e.target.value)} />
      <GroupChecks orgId={org.id} selected={groupIds} onChange={setGroupIds} />
    </PlatformDialog>
  );
}

export function editUserDialog(org: Organization, u: OrganizationUser, done: () => void): void {
  store.openDialog({ render: (close) => <EditUser org={org} u={u} close={close} done={done} /> });
}

function EditUser({ org, u, close, done }: { org: Organization; u: OrganizationUser; close: () => void; done: () => void }) {
  const t = useT();
  const [name, setName] = useState(u.name);
  const [department, setDepartment] = useState(u.department || '');
  const [groupIds, setGroupIds] = useState<string[]>(u.groups.map((g) => g.id));
  return (
    <PlatformDialog
      title={t('platform.user.editTitle', { name: u.name })}
      sub={u.email}
      close={close}
      label={t('common.save')}
      onSave={() =>
        api.updateOrganizationUser(org.id, u.id, { name: name.trim(), department: department.trim() || null, groupIds }).then((next) => {
          store.toast2(t('platform.user.saved'), next.name);
          done();
        })
      }
    >
      <label htmlFor="euName">{t('platform.user.name')}</label>
      <input id="euName" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
      <label htmlFor="euDept">{t('platform.user.department')}</label>
      <input id="euDept" value={department} maxLength={120} onChange={(e) => setDepartment(e.target.value)} />
      <GroupChecks orgId={org.id} selected={groupIds} onChange={setGroupIds} />
    </PlatformDialog>
  );
}

export function resetPasswordDialog(org: Organization, u: OrganizationUser, done: () => void): void {
  store.openDialog({ render: (close) => <ResetPassword org={org} u={u} close={close} done={done} /> });
}

function ResetPassword({ org, u, close, done }: { org: Organization; u: OrganizationUser; close: () => void; done: () => void }) {
  const t = useT();
  const [password, setPassword] = useState('');
  return (
    <PlatformDialog
      title={t('platform.user.resetTitle', { name: u.name })}
      close={close}
      label={t('platform.user.reset')}
      note={resetNote()}
      onRefused={() => setPassword('')}
      onSave={() =>
        api.resetOrganizationUserPassword(org.id, u.id, password).then(() => {
          setPassword('');
          store.toast2(t('platform.user.passwordReset'), u.name);
          done();
        })
      }
    >
      <label htmlFor="rpPassword">{t('platform.user.newPassword')}</label>
      <input id="rpPassword" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
    </PlatformDialog>
  );
}

/** `Disable <name>?` in the reference's `confirmDialog` with a `danger` button. */
export function disableUserDialog(org: Organization, u: OrganizationUser, done: () => void): void {
  confirmDialog(
    t('platform.user.disableTitle', { name: u.name }),
    t('platform.user.disableBody'),
    t('common.disable'),
    () =>
      attempt(() => api.disableOrganizationUser(org.id, u.id)).then((res) => {
        if (!res) return;
        store.toast2(t('platform.user.disabled'), u.name);
        done();
      }),
    true,
  );
}

/** `Remove <name> from <organization>?` in the reference's `confirmDialog` with a `danger` button. */
export function removeUserDialog(org: Organization, u: OrganizationUser, done: () => void): void {
  confirmDialog(
    t('platform.user.removeTitle', { name: u.name, organization: org.name }),
    removeText(org.name),
    t('platform.user.remove'),
    () =>
      attempt(() => api.removeOrganizationUser(org.id, u.id)).then((res) => {
        if (res === null) return;
        store.toast2(t('platform.user.removed'), u.name);
        done();
      }),
    true,
  );
}

/** The body of the removal confirmation. */
export const removeText = (organization: string): string => t('platform.user.removeBody', { organization });

export function enableUser(org: Organization, u: OrganizationUser, done: () => void): Promise<void> {
  return attempt(() => api.enableOrganizationUser(org.id, u.id)).then((res) => {
    if (!res) return;
    store.toast2(t('platform.user.enabled'), u.name);
    done();
  });
}
