/**
 * What the admin portal's buttons do, and the dialogs they open: settings, the typed `disable`
 * confirmation, rename, bind and unbind, source enable, disable and removal, company removal,
 * group edit, members and roles, the role-to-groups list, the scope choice and the agent
 * registry. Behaviour and copy from reference/ontaix-studio-reference.html lines 947-1053.
 * Ontology changes are proposals; settings, directory and source-state changes are immediate.
 */
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';

import { api } from '../api/client';
import type { Group, ProposalDraft, Scope, User } from '../api/types';
import { DOMAIN_TEMPLATES } from '../canvas/constants';
import type { Company, Link, Node } from '../canvas/types';
import { title } from '../nl/parser';
import { DialogFrame } from '../shell/Dialog';
import { store } from '../store/store';
import { attempt, directory, failed, fetchAll, invalidateDirectory } from './adminData';
import { isDisableConfirmed } from './confirmText';
import { List, type Column } from './List';
import { en } from './listModel';
import { roleLabel, roleName, ROLE_NAMES } from './roles';
import { Tg, type SettingKey } from './Toggle';

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** Re-reads the directory and redraws the portal from scratch. */
export function renderAdmin(): void {
  invalidateDirectory();
  store.renderAdmin();
}

/** A small dialog with Cancel and one action button, the reference's `confirmDialog`. */
export function confirmDialog(heading: string, body: ReactNode, label: string, onYes: () => void, danger?: boolean): void {
  store.openDialog({
    title: heading,
    body,
    small: true,
    buttons: [{ label: 'Cancel' }, { label, cls: danger ? 'danger' : 'primary', onClick: () => onYes() }],
  });
}

/**
 * Sends a draft; the success feedback runs only once the server has accepted it. A refusal
 * shows the store's refusal toast instead.
 */
function proposeThen(draft: ProposalDraft, accepted: () => void): void {
  void store.propose(draft).then((p) => {
    if (p) accepted();
  }, failed);
}

/** Runs a proposal-creating call; the success feedback runs only when it was accepted. */
function attemptThen<T>(call: () => Promise<T>, accepted: () => void): void {
  void attempt(call).then((r) => {
    if (r !== null) accepted();
  });
}

// ------------------------------------------------------------ settings

/** Flips a tenant setting; turning off "Companies may interact" goes through the typed confirmation. */
export function changeSetting(k: SettingKey): void {
  const st = store.ui.settings;
  if (!st) return;
  if (k === 'crossCompany' && st.crossCompany) {
    disableCrossCompany();
    return;
  }
  void attempt(() => api.patchSettings({ [k]: !st[k] })).then((next) => {
    if (!next) return;
    store.ui.settings = next;
    store.applySettings();
    renderAdmin();
  });
}

export function changeRefresh(value: string): void {
  void attempt(() => api.patchSettings({ refresh: value as '5 min' | '15 min' | '1 h' | 'daily' })).then((next) => {
    if (next) store.ui.settings = next;
  });
}

const crossLinks = (): Link[] => store.s.links.filter((l) => l.a.company !== l.b.company && !l.dying);

function disableCrossCompany(): void {
  const xl = crossLinks();
  const done = (removed: number) => {
    store.toast2('Disabled', `${plural(removed, 'cross-company relationship')} removed`);
    store.applySettings();
    renderAdmin();
  };
  if (!xl.length) {
    void attempt(() => api.patchSettings({ crossCompany: false })).then((next) => {
      if (!next) return;
      store.ui.settings = next;
      done(0);
    });
    return;
  }
  store.openDialog({
    render: (close) => (
      <CrossCompanyDialog
        links={xl}
        close={close}
        onConfirm={(typed) => {
          void attempt(() => api.disableCrossCompany(typed)).then((res) => {
            if (!res) return;
            store.ui.settings = res.settings;
            done(res.removedRelations);
          });
        }}
      />
    ),
  });
}

function CrossCompanyDialog({ links, close, onConfirm }: { links: Link[]; close: () => void; onConfirm: (typed: string) => void }) {
  const [typed, setTyped] = useState('');
  const [bad, setBad] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const ok = isDisableConfirmed(typed);
  useEffect(() => {
    const t = setTimeout(() => input.current?.focus(), 40);
    return () => clearTimeout(t);
  }, []);
  const pairs = [...new Set(links.map((l) => `${l.a.company?.name} ↔ ${l.b.company?.name}`))];
  const submit = () => {
    if (!isDisableConfirmed(typed)) {
      setBad(true);
      input.current?.focus();
      return;
    }
    close();
    onConfirm(typed.trim().toLowerCase());
  };
  return (
    <DialogFrame
      title="Disable interaction between companies?"
      sub="this cannot be undone by re-enabling"
      onClose={close}
      footer={
        <>
          <button className="btn " data-i={0} onClick={close}>
            Cancel
          </button>
          <button className="btn danger" data-i={1} disabled={!ok} style={{ opacity: ok ? 1 : 0.5 }} onClick={submit}>
            Disable and remove relationships
          </button>
        </>
      }
    >
      <p style={{ margin: '0 0 10px' }}>
        The companies below are already interacting. Disabling removes <b>{plural(links.length, 'relationship')}</b> between them, immediately and
        without a proposal. Each company keeps its own concepts, relations and bindings.
      </p>
      <p style={{ margin: '0 0 6px' }}>
        <b>{pairs.join(' · ')}</b>
      </p>
      <div className="discover" style={{ fontFamily: 'inherit', fontSize: '12.5px' }}>
        {links.slice(0, 6).map((l, i) => (
          <Fragment key={i}>
            {i ? <br /> : null}
            {`${l.a.label} `}
            <em style={{ color: 'var(--ink-3)', fontStyle: 'normal' }}>{l.label}</em>
            {` ${l.b.label}`}
          </Fragment>
        ))}
        {links.length > 6 ? (
          <div>
            <span>{`and ${links.length - 6} more`}</span>
          </div>
        ) : null}
      </div>
      <div className="form" style={{ marginTop: '14px', gridTemplateColumns: '1fr' }}>
        <label>
          Type <b style={{ color: 'var(--conflict)' }}>disable</b> to confirm
        </label>
        <input
          id="ccConfirm"
          ref={input}
          placeholder="disable"
          autoComplete="off"
          value={typed}
          style={bad ? { borderColor: 'var(--conflict)' } : undefined}
          onChange={(e) => {
            setTyped(e.target.value);
            setBad(false);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && isDisableConfirmed(typed)) submit();
          }}
        />
      </div>
    </DialogFrame>
  );
}

// ------------------------------------------------------------ appearance

let colourTimer: ReturnType<typeof setTimeout> | null = null;

/** Applies a colour at once and saves it after the picker settles. */
export function changeColour(key: string, value: string): void {
  const ap = store.ui.appearance;
  if (!ap) return;
  const patch = key === '__accent' ? { accent: value } : key === '__source' ? { source: value } : { colors: { [key]: value } };
  store.ui.appearance = {
    ...ap,
    accent: key === '__accent' ? value : ap.accent,
    source: key === '__source' ? value : ap.source,
    colors: key.startsWith('__') ? ap.colors : { ...ap.colors, [key]: value },
  };
  store.applyColors();
  if (colourTimer) clearTimeout(colourTimer);
  colourTimer = setTimeout(() => {
    colourTimer = null;
    void attempt(() => api.patchAppearance(patch));
  }, 300);
}

export function resetColours(): void {
  void attempt(() => api.resetAppearance()).then((ap) => {
    if (!ap) return;
    store.ui.appearance = ap;
    store.applyColors();
    store.toast2('Reset', 'default colours');
    renderAdmin();
  });
}

// ------------------------------------------------------------ entities, relations, bindings

export function renameDialog(n: Node): void {
  store.openDialog({
    title: `Rename ${n.label}`,
    small: true,
    body: (
      <div className="form" style={{ gridTemplateColumns: '90px 1fr' }}>
        <label>New name</label>
        <input id="rnName" defaultValue={n.label} />
      </div>
    ),
    buttons: [
      { label: 'Cancel' },
      {
        label: 'Propose',
        cls: 'primary',
        onClick: (bk) => {
          const name = title((bk.querySelector<HTMLInputElement>('#rnName')?.value || '').trim());
          if (name && name !== n.label && n.sid)
            proposeThen({ type: 'change', changeKind: 'rename', payload: { conceptId: n.sid, newLabel: name } }, () => {
              store.toast2('Proposed', `rename to ${name}`);
              renderAdmin();
            });
        },
      },
    ],
  });
}

export function deleteNodeDialog(n: Node, rels: number): void {
  confirmDialog(
    `Delete ${n.label}?`,
    `This proposes a change for approval. Its ${plural(rels, 'relation')} and any specialisation of it go with it.`,
    'Propose deletion',
    () => {
      if (n.sid)
        proposeThen({ type: 'change', changeKind: 'delete_concept', payload: { conceptId: n.sid } }, () => {
          store.toast2('Proposed', `deletion of ${n.label}`);
          renderAdmin();
        });
    },
    true,
  );
}

export function deleteRelationDialog(l: Link, name: string): void {
  confirmDialog(
    `Delete “${name}”?`,
    'This proposes a change for approval.',
    'Propose deletion',
    () => {
      if (l.sid)
        proposeThen({ type: 'change', changeKind: 'remove_relation', payload: { relationId: l.sid } }, () => {
          store.caption('One proposal', `Removing “${l.a.label} ${l.label} ${l.b.label}” is waiting for your approval.`);
          renderAdmin();
        });
    },
    true,
  );
}

export function bindDialog(n: Node): void {
  const srcs = store.s.nodes.filter((x) => x.kind === 'source' && x.company === n.company && !x.pending && !x.dying);
  if (!srcs.length) {
    store.toast2('No source', `add a data source for ${n.company?.name} first`);
    return;
  }
  store.openDialog({
    title: `Bind ${n.label}`,
    small: true,
    body: (
      <div className="form" style={{ gridTemplateColumns: '90px 1fr' }}>
        <label>Source</label>
        <select id="bdSrc">
          {srcs.map((x) => (
            <option key={x.id} value={x.id}>{`${x.label} · ${x.sub}`}</option>
          ))}
        </select>
        <label></label>
        <small style={{ color: 'var(--ink-3)' }}>The binding is proposed; attributes found in the schema follow as their own proposals.</small>
      </div>
    ),
    buttons: [
      { label: 'Cancel' },
      {
        label: 'Propose binding',
        cls: 'primary',
        onClick: (bk) => {
          const id = bk.querySelector<HTMLSelectElement>('#bdSrc')?.value;
          const src = srcs.find((x) => String(x.id) === id);
          if (!src || !src.sid || !n.sid) return;
          proposeThen({ type: 'bind', sourceId: src.sid, conceptIds: [n.sid] }, () => {
            store.toast2('Proposed', `${n.label} bound to ${src.label}`);
            renderAdmin();
          });
        },
      },
    ],
  });
}

export function unbindDialog(n: Node, source: string, attrs: number): void {
  confirmDialog(
    `Unbind ${n.label} from ${source}?`,
    `This proposes a change for approval. ${n.label} keeps its ${attrs} approved attributes as declared; record count and freshness disappear.`,
    'Propose unbinding',
    () => {
      const link = store.s.links.find((l) => l.kind === 'bind' && l.b === n && !l.pending);
      const sid = link?.sid;
      if (sid)
        attemptThen(
          () => api.proposeUnbind(sid),
          () => {
            store.toast2('Proposed', `unbinding of ${n.label}`);
            renderAdmin();
          },
        );
    },
    true,
  );
}

// ------------------------------------------------------------ sources and companies

export function toggleSource(n: Node): void {
  const sid = n.sid;
  if (!sid) return;
  const doIt = () => {
    const off = !n.disabled;
    void attempt(() => (off ? api.disableSource(sid) : api.enableSource(sid))).then((src) => {
      if (!src) return;
      n.disabled = src.disabled;
      store.toast2(src.disabled ? 'Disabled' : 'Enabled', n.label);
      renderAdmin();
    });
  };
  if (n.disabled) {
    doIt();
    return;
  }
  const fed = store.s.links.filter((l) => l.kind === 'bind' && l.a === n).length;
  confirmDialog(
    `Disable ${n.label}?`,
    <>
      {`Syncing stops. The ${plural(fed, 'concept')} it feeds keep their attributes; counts and freshness are marked `}
      <b>paused</b> until you enable it again.
    </>,
    'Disable',
    doIt,
  );
}

export function removeSourceDialog(n: Node): void {
  const fed = store.s.links.filter((l) => l.kind === 'bind' && l.a === n).map((l) => l.b.label);
  confirmDialog(
    `Delete ${n.label}?`,
    fed.length ? (
      <>
        This proposes a change for approval. The following concepts would lose their binding: <b>{fed.join(', ')}</b>. They keep their attributes as
        declared.
      </>
    ) : (
      'This proposes a change for approval. Nothing is bound to it.'
    ),
    'Propose deletion',
    () => {
      const sid = n.sid;
      if (sid)
        attemptThen(
          () => api.proposeRemoveSource(sid),
          () => {
            store.caption('One proposal', `Removing ${n.label} is waiting for approval.`);
            store.toast2('Proposed', `deletion of ${n.label} · approve it on the canvas`);
            renderAdmin();
          },
        );
    },
    true,
  );
}

export function removeCompanyDialog(c: Company): void {
  const cells = store.s.nodes.filter((x) => x.company === c).length;
  confirmDialog(
    `Remove ${c.name}?`,
    `This proposes a change for approval. Its ${cells} cells, its sources and its equivalences with other companies would leave the view.`,
    'Propose removal',
    () => {
      const sid = c.sid;
      if (sid)
        attemptThen(
          () => api.proposeRemoveCompany(sid),
          () => {
            store.toast2('Proposed', `removal of ${c.name} · approve it on the canvas`);
            renderAdmin();
          },
        );
    },
    true,
  );
}

// ------------------------------------------------------------ groups, roles, agents

/** Tenant, each company, each domain product family: the reference's `SCOPES()`. */
export function localScopes(): Scope[] {
  return [
    { kind: 'tenant', companyId: null, domainKey: null, label: 'Tenant' },
    ...store.s.companies.map((c) => ({ kind: 'company' as const, companyId: c.sid, domainKey: null, label: c.name })),
    ...DOMAIN_TEMPLATES.map((t) => ({ kind: 'domain' as const, companyId: null, domainKey: t.key, label: t.name })),
  ];
}

export function groupEdit(g: Group | null): void {
  store.openDialog({
    title: g ? `Edit ${g.name}` : 'Create a group',
    small: true,
    body: (
      <div className="form" style={{ gridTemplateColumns: '100px 1fr' }}>
        <label>Name</label>
        <input id="gName" defaultValue={g ? g.name : ''} placeholder="e.g. Quality · owners" />
        <label>Description</label>
        <input id="gDesc" defaultValue={g ? g.description : ''} placeholder="what this group is for" />
      </div>
    ),
    buttons: [
      { label: 'Cancel' },
      {
        label: g ? 'Save' : 'Create',
        cls: 'primary',
        onClick: (bk) => {
          const nameInput = bk.querySelector<HTMLInputElement>('#gName');
          const name = (nameInput?.value || '').trim();
          if (!name) {
            nameInput?.focus();
            return false;
          }
          const description = (bk.querySelector<HTMLInputElement>('#gDesc')?.value || '').trim();
          if (g) {
            void attempt(() => api.updateGroup(g.id, { name, description })).then((r) => {
              if (!r) return;
              store.toast2('Saved', name);
              renderAdmin();
            });
          } else {
            void attempt(() => api.createGroup({ name, description })).then((ng) => {
              if (!ng) return;
              store.toast2('Created', name);
              renderAdmin();
              setTimeout(() => groupMembers(ng), 150);
            });
          }
        },
      },
    ],
  });
}

interface MemberRow extends Record<string, unknown> {
  id: string;
  name: string;
  email: string;
  dept: string;
  company: string;
  on: boolean;
}

export function groupMembers(g: Group): void {
  store.openDialog({ render: (close) => <MembersDialog g={g} close={close} /> });
}

function memberRows(users: User[], g: Group): MemberRow[] {
  return users.map((u) => ({
    id: u.id,
    name: u.name,
    email: u.email,
    dept: u.department || '',
    company: u.companyName || '',
    on: u.groups.some((x) => x.id === g.id),
  }));
}

function MembersDialog({ g, close }: { g: Group; close: () => void }) {
  const [rows, setRows] = useState<MemberRow[]>(() => memberRows(directory.users, g));
  useEffect(() => {
    if (directory.users.length) return;
    void fetchAll((p) => api.listUsers(p))
      .then((users) => setRows(memberRows(users, g)))
      .catch((err: unknown) => failed(err, 'Unavailable'));
  }, [g]);
  const toggle = (r: MemberRow) => {
    const on = !r.on;
    void attempt(() => (on ? api.addGroupMember(g.id, r.id) : api.removeGroupMember(g.id, r.id))).then((res) => {
      if (res === null) return;
      setRows((cur) => cur.map((x) => (x.id === r.id ? { ...x, on } : x)));
    });
  };
  const columns: Column[] = [
    { label: 'User', key: 'name' },
    { label: 'Email', key: 'email' },
    { label: 'Department', key: 'dept' },
    { label: 'Company', key: 'company' },
    { label: 'Member', w: '100px' },
  ];
  return (
    <ListDialogFrame
      title={`Members · ${g.name}`}
      sub="add or remove users · the directory is Ontaix’s own"
      close={close}
      buttons={[{ label: 'Done', cls: 'primary', onClick: () => renderAdmin() }]}
    >
      <List
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        searchKeys={['name', 'email', 'dept', 'company']}
        filterKey="dept"
        pageSize={40}
        renderRow={(r) => (
          <>
            <td>
              <b>{r.name}</b>
            </td>
            <td style={{ color: 'var(--ink-2)' }}>{r.email}</td>
            <td>{r.dept}</td>
            <td>{r.company}</td>
            <td>
              <Tg on={r.on} data-fn="member" onClick={() => toggle(r)} />
            </td>
          </>
        )}
        footer={() => `${rows.filter((x) => x.on).length} members in the group`}
      />
    </ListDialogFrame>
  );
}

export function groupRoles(g: Group): void {
  store.openDialog({ render: (close) => <RolesDialog g={g} close={close} /> });
}

function RolesDialog({ g, close }: { g: Group; close: () => void }) {
  const [roles, setRoles] = useState(g.roles);
  const roleSel = useRef<HTMLSelectElement>(null);
  const scopeSel = useRef<HTMLSelectElement>(null);
  const scopes = localScopes();
  const add = () => {
    const role = roleSel.current?.value || ROLE_NAMES[0],
      label = scopeSel.current?.value || 'Tenant';
    const scope = scopes.find((x) => x.label === label);
    if (!scope || roles.some((r) => roleLabel(r.role) === role && r.scope.label === label)) return;
    void attempt(() => api.addGroupRole(g.id, { role: roleName(role), scope })).then((a) => {
      if (a) setRoles((cur) => [...cur, a]);
    });
  };
  const remove = (id: string) => {
    void attempt(() => api.removeGroupRole(g.id, id)).then((res) => {
      if (res !== null) setRoles((cur) => cur.filter((r) => r.id !== id));
    });
  };
  return (
    <DialogFrame
      title={`Roles · ${g.name}`}
      sub="a role plus the scope it applies to"
      onClose={close}
      footer={
        <button
          className="btn primary"
          data-i={0}
          onClick={() => {
            close();
            store.toast2('Saved', `roles of ${g.name}`);
            renderAdmin();
          }}
        >
          Done
        </button>
      }
    >
      <div className="chips2" id="grRoles">
        {roles.length ? (
          roles.map((r, i) => (
            <span key={r.id}>
              {`${roleLabel(r.role)} · ${r.scope.label}`}
              <b data-i={i} title="Remove" onClick={() => remove(r.id)}>
                ×
              </b>
            </span>
          ))
        ) : (
          <small style={{ color: 'var(--ink-3)' }}>No role yet.</small>
        )}
      </div>
      <div className="form" style={{ marginTop: '14px', gridTemplateColumns: '80px 1fr 1fr auto' }}>
        <label>Add</label>
        <select id="grRole" ref={roleSel}>
          {ROLE_NAMES.map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
        <select id="grScope" ref={scopeSel}>
          {scopes.map((x) => (
            <option key={`${x.kind}:${x.label}`}>{x.label}</option>
          ))}
        </select>
        <button className="btn" id="grAdd" onClick={add}>
          Add
        </button>
      </div>
      <p style={{ margin: '12px 0 0', color: 'var(--ink-3)', fontSize: '12px' }}>
        Owner and Governor on the same scope is what certification needs. Administrator only applies at Tenant scope.
      </p>
    </DialogFrame>
  );
}

export function deleteGroupDialog(g: Group): void {
  const nroles = g.roles.length;
  confirmDialog(
    `Delete “${g.name}”?`,
    `Its ${plural(g.memberCount, 'member')} lose the ${plural(nroles, 'role assignment')} it carries. Users themselves are not deleted.`,
    'Delete group',
    () => {
      void attempt(() => api.deleteGroup(g.id)).then((res) => {
        if (res === null) return;
        store.toast2('Deleted', g.name);
        renderAdmin();
      });
    },
    true,
  );
}

interface HoldRow extends Record<string, unknown> {
  id: string;
  g: Group;
  name: string;
  desc: string;
  members: number;
  scopes: string;
  on: boolean;
}

/** Which groups hold a role, and on which scope. */
export function roleGroups(role: string): void {
  store.openDialog({ render: (close) => <RoleGroupsDialog role={role} close={close} /> });
}

const holdRow = (g: Group, role: string): HoldRow => {
  const mine = g.roles.filter((r) => roleLabel(r.role) === role);
  return {
    id: g.id,
    g,
    name: g.name,
    desc: g.description,
    members: g.memberCount,
    scopes: mine.map((r) => r.scope.label).join(', ') || '—',
    on: mine.length > 0,
  };
};

function RoleGroupsDialog({ role, close }: { role: string; close: () => void }) {
  const [rows, setRows] = useState<HoldRow[]>(() => directory.groups.map((g) => holdRow(g, role)));
  const replace = (g: Group) => setRows((cur) => cur.map((x) => (x.id === g.id ? holdRow(g, role) : x)));
  const hold = (r: HoldRow) => {
    if (r.on) {
      const drop = r.g.roles.filter((a) => roleLabel(a.role) === role);
      void Promise.allSettled(drop.map((a) => api.removeGroupRole(r.g.id, a.id))).then((results) => {
        const removed = drop.filter((_, i) => results[i].status === 'fulfilled');
        replace({ ...r.g, roles: r.g.roles.filter((a) => !removed.includes(a)) });
        const refusal = results.find((x): x is PromiseRejectedResult => x.status === 'rejected');
        if (refusal) failed(refusal.reason);
      });
      return;
    }
    const scopes = localScopes();
    store.openDialog({
      title: `${role} on which scope?`,
      small: true,
      body: (
        <div className="form" style={{ gridTemplateColumns: '80px 1fr' }}>
          <label>Scope</label>
          <select id="rsScope">
            {scopes.map((x) => (
              <option key={`${x.kind}:${x.label}`}>{x.label}</option>
            ))}
          </select>
        </div>
      ),
      buttons: [
        { label: 'Cancel' },
        {
          label: 'Give role',
          cls: 'primary',
          onClick: (bk) => {
            const label = bk.querySelector<HTMLSelectElement>('#rsScope')?.value;
            const scope = scopes.find((x) => x.label === label);
            if (!scope) return;
            void attempt(() => api.addGroupRole(r.g.id, { role: roleName(role), scope })).then((a) => {
              if (a) replace({ ...r.g, roles: [...r.g.roles, a] });
            });
          },
        },
      ],
    });
  };
  const columns: Column[] = [
    { label: 'Group', key: 'name' },
    { label: 'Description', key: 'desc' },
    { label: 'Members', key: 'members', num: true },
    { label: 'Scope', key: 'scopes' },
    { label: 'Holds role', w: '100px' },
  ];
  return (
    <ListDialogFrame
      title={`${role} · groups`}
      sub="which Ontaix groups hold this role, and on which scope"
      close={close}
      buttons={[{ label: 'Done', cls: 'primary', onClick: () => renderAdmin() }]}
    >
      <List
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        searchKeys={['name', 'desc', 'scopes']}
        pageSize={40}
        renderRow={(r) => (
          <>
            <td>
              <b>{r.name}</b>
            </td>
            <td style={{ color: 'var(--ink-2)' }}>{r.desc}</td>
            <td className="num">{r.members}</td>
            <td>{r.scopes}</td>
            <td>
              <Tg on={r.on} data-fn="hold" onClick={() => hold(r)} />
            </td>
          </>
        )}
        footer={(l) => `${l.filter((x) => x.on).length} groups hold ${role}`}
      />
    </ListDialogFrame>
  );
}

interface AgentRow extends Record<string, unknown> {
  id: string;
  name: string;
  platform: string;
  domain: string;
  owner: string;
  reads: number;
  cost: number;
  on: boolean;
}

export function agentRegistry(): void {
  store.openDialog({ render: (close) => <RegistryDialog close={close} /> });
}

function RegistryDialog({ close }: { close: () => void }) {
  const [rows, setRows] = useState<AgentRow[]>([]);
  useEffect(() => {
    void fetchAll((p) => api.listAgents(p))
      .then((agents) =>
        setRows(
          agents.map((a) => ({
            id: a.id,
            name: a.name,
            platform: a.platform,
            domain: a.domainName || '—',
            owner: a.owner,
            reads: a.reads,
            cost: a.costEur,
            on: a.access,
          })),
        ),
      )
      .catch((err: unknown) => failed(err, 'Unavailable'));
  }, []);
  const toggle = (r: AgentRow) => {
    void attempt(() => api.updateAgent(r.id, !r.on)).then((a) => {
      if (a) setRows((cur) => cur.map((x) => (x.id === r.id ? { ...x, on: a.access } : x)));
    });
  };
  const columns: Column[] = [
    { label: 'Agent', key: 'name' },
    { label: 'Platform', key: 'platform' },
    { label: 'Domain product', key: 'domain' },
    { label: 'Owner', key: 'owner' },
    { label: 'Reads · month', key: 'reads', num: true },
    { label: 'Cost · month', key: 'cost', num: true },
    { label: 'Access', w: '100px' },
  ];
  return (
    <ListDialogFrame
      title="Agent registry"
      sub="every agent, from every platform, that can read this model through the gateway"
      close={close}
      buttons={[{ label: 'Close' }]}
    >
      <List
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        searchKeys={['name', 'platform', 'domain', 'owner']}
        filterKey="platform"
        pageSize={50}
        renderRow={(r) => (
          <>
            <td>
              <b>{r.name}</b>
            </td>
            <td>{r.platform}</td>
            <td>{r.domain}</td>
            <td>{r.owner}</td>
            <td className="num">{en(r.reads)}</td>
            <td className="num">{`€ ${en(r.cost)}`}</td>
            <td>
              <Tg on={r.on} data-fn="toggle" onClick={() => toggle(r)} />
            </td>
          </>
        )}
        footer={(l) => `${en(l.filter((x) => x.on).length)} with access · € ${en(l.reduce((a, x) => a + x.cost, 0))}`}
      />
    </ListDialogFrame>
  );
}

/** The large list dialog (`listDialog`): a list host in the body; the search box takes focus. */
function ListDialogFrame({
  title: heading,
  sub,
  close,
  buttons,
  children,
}: {
  title: string;
  sub: string;
  close: () => void;
  buttons: { label: string; cls?: string; onClick?: () => void }[];
  children: ReactNode;
}) {
  const back = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const t = setTimeout(() => back.current?.querySelector<HTMLInputElement>('.search')?.focus(), 40);
    return () => clearTimeout(t);
  }, []);
  return (
    <DialogFrame
      title={heading}
      sub={sub}
      large
      onClose={close}
      backRef={back}
      footer={buttons.map((b, i) => (
        <button
          key={i}
          className={`btn ${b.cls || ''}`}
          data-i={i}
          onClick={() => {
            b.onClick?.();
            close();
          }}
        >
          {b.label}
        </button>
      ))}
    >
      <div className="lst-host">{children}</div>
    </DialogFrame>
  );
}

