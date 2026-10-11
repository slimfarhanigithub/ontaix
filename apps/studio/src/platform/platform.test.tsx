import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';

import type { Organization, OrganizationUser, PlatformAuditEntry, Session } from '../api/types';
import { AccountControls } from '../auth/AccountControls';
import { auth } from '../auth/authStore';
import { CSRF, json, noContent, platformSession, problem, stubFetch, type FetchStub } from '../auth/fetchStub';
import { Header } from '../shell/Header';
import { store } from '../store/store';
import { createEventBus } from '../api/events';
import { createMockServer } from '../api/mock/server';
import type { Scene } from '../api/types';
import { actingText, minutesLeft, PlatformAccessBanner } from '../auth/PlatformAccessBanner';
import { AuditLog } from '../admin/pages/GovernancePages';
import { directory } from '../admin/adminData';
import { ADD_USER_NOTE, RESET_NOTE, userStatus } from './OrganizationUsers';
import { PlatformPortal } from './PlatformPortal';

// The portal renders lists and dialogs, which jsdom lays out slowly under a full run.
vi.setConfig({ testTimeout: 30_000 });

const flush = () => act(() => new Promise((r) => setTimeout(r, 0)));
const input = (id: string) => document.getElementById(id) as HTMLInputElement;
const topDialog = () => {
  const all = document.querySelectorAll('.dlg');
  return all[all.length - 1] as HTMLElement;
};
const dialogTitle = () => topDialog().querySelector('.dh b')?.textContent;
const dialogMsg = () => topDialog().querySelector('.msg') as HTMLElement | null;
const footerButton = (label: string) => within(topDialog().querySelector('.df') as HTMLElement).getByRole('button', { name: label });
/** The list row holding this text; a toast may repeat it outside the table. */
const rowOf = (name: string) => screen.getAllByText(name).map((el) => el.closest('tr')).find((tr) => tr) as HTMLElement;
/** The row's primary button, or the item of its More actions menu, which the call opens. */
const rowAction = (name: string, label: string) => {
  const row = within(rowOf(name));
  const visible = row.queryByRole('button', { name: label });
  if (visible) return visible;
  fireEvent.click(row.getByRole('button', { name: 'More actions' }));
  return screen.getByRole('menuitem', { name: label });
};
/** The labels of a row's actions: the visible buttons, then the items of its More actions menu. */
const rowActionLabels = (name: string) => {
  const row = rowOf(name);
  const visible = [...row.querySelectorAll('.act button:not(.more)')].map((b) => b.textContent);
  const more = row.querySelector('.act button.more') as HTMLButtonElement | null;
  if (!more) return visible;
  fireEvent.click(more);
  const items = [...document.querySelectorAll('.dr-menu [role^="menuitem"]')].map((b) => b.textContent);
  fireEvent.keyDown(document.querySelector('.dr-menu') as HTMLElement, { key: 'Escape' });
  return [...visible, ...items];
};

const fresh = (n: number) => `test-password-${n}-${'x'.repeat(8)}`;

const org = (over: Partial<Organization> = {}): Organization => ({
  id: 'org-1',
  name: 'Acme',
  slug: 'acme',
  companyMode: 'multiple',
  status: 'active',
  companies: 2,
  users: 3,
  createdAt: '2026-09-01T09:00:00Z',
  disabledAt: null,
  ...over,
});

const user = (over: Partial<OrganizationUser> = {}): OrganizationUser => ({
  id: 'u-1',
  accountId: 'acc-1',
  email: 'ana@acme.example',
  name: 'Ana',
  department: 'Sales',
  status: 'active',
  mustChangePassword: false,
  locked: false,
  groups: [{ id: 'g-1', name: 'Administrators' }],
  createdAt: '2026-09-02T09:00:00Z',
  lastSignInAt: null,
  ...over,
});

const paged = <T,>(items: T[]) => json(200, { items, page: 1, pageSize: 200, total: items.length });

/** A platform session acting inside an organization, with 59 and a half minutes of its hour left. */
const actingSession = (id: string, name: string, over: Partial<Session> = {}): Session =>
  platformSession({
    csrfToken: 'acting-csrf-'.padEnd(43, 'z'),
    acting: { organization: { id, name, slug: id }, since: new Date(Date.now() - 30_000).toISOString(), until: new Date(Date.now() + 59.5 * 60_000).toISOString() },
    ...over,
  });

/** The mock server's fresh scene, its home company renamed. */
function sceneOf(company: string): Scene {
  const scene = createMockServer(createEventBus()).handle('GET', '/scene').body as Scene;
  scene.companies[0].name = company;
  return scene;
}

const ORGS = [org(), org({ id: 'org-2', name: 'Beta Ltd', slug: 'beta', companyMode: 'single', status: 'disabled', companies: 1, users: 0, disabledAt: '2026-09-20T09:00:00Z' })];
const USERS = [user(), user({ id: 'u-2', accountId: 'acc-2', email: 'bo@acme.example', name: 'Bo', status: 'disabled', groups: [] }), user({ id: 'u-3', accountId: 'acc-3', email: 'cy@acme.example', name: 'Cy', mustChangePassword: true })];
const GROUPS = [
  { id: 'g-1', name: 'Administrators', description: 'Administrator at tenant scope', memberCount: 1, roles: [] },
  { id: 'g-2', name: 'Builders', description: 'Builder at tenant scope', memberCount: 0, roles: [] },
];
const AUDIT: PlatformAuditEntry[] = [
  { id: 2, at: '2026-09-30T08:30:00Z', actor: { accountId: 'acc-sa', email: 'admin@platform.example' }, action: 'organization_created', ok: true, organization: { id: 'org-1', name: 'Acme', slug: 'acme' }, what: 'Created the organization Acme', clientIp: '10.0.0.1' },
  { id: 1, at: '2026-09-30T08:00:00Z', actor: null, action: 'sign_in_failed', ok: false, organization: null, what: 'A sign-in with an unknown email failed', clientIp: '10.0.0.2' },
];

function routes(): FetchStub {
  return stubFetch({
    'GET /auth/session': json(200, platformSession()),
    'GET /admin/organizations': paged(ORGS),
    'GET /admin/organizations/org-1/users': paged(USERS),
    'GET /admin/organizations/org-1/groups': json(200, GROUPS),
    'GET /admin/audit': paged(AUDIT),
  });
}

async function openPortal(): Promise<FetchStub> {
  const stub = routes();
  await auth.boot();
  render(<PlatformPortal />);
  await flush();
  return stub;
}

async function openUsers(): Promise<FetchStub> {
  const stub = await openPortal();
  fireEvent.click(rowAction('Acme', 'Users'));
  await flush();
  expect(dialogTitle()).toBe('Users of Acme');
  return stub;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  store.ui.dialogs = [];
  store.ui.toasts = [];
});

describe('the platform portal', () => {
  it('is the reference admin window with the Platform nav, the account controls and no ×', async () => {
    await openPortal();
    const win = document.querySelector('#platform.admin.on .win') as HTMLElement;
    expect(win.querySelector('.head #platformTitle')?.textContent).toBe('Ontology Builder platform');
    expect(win.querySelector('.head .x')).toBeNull();
    expect(win.querySelector('nav .grp')?.textContent).toBe('Platform');
    expect([...win.querySelectorAll('nav button')].map((b) => b.textContent)).toEqual(['Organizations', 'Platform audit log']);
    const account = win.querySelector('.head #adminAccount') as HTMLElement;
    expect(account.querySelector('span')?.textContent).toBe('admin@platform.example');
    expect([...account.querySelectorAll('.btn')].map((b) => b.textContent)).toEqual(['Change password', 'Sign out']);
  });

  it('lists the organizations with their companies, users, status and created date', async () => {
    await openPortal();
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('Organizations');
    expect(document.querySelector('.lead')?.textContent).toBe(
      'Each organization is its own instance: its users see only its data. Only a super admin creates organizations and their accounts.',
    );
    expect([...document.querySelectorAll('.tbl th')].map((th) => th.textContent)).toEqual(['Name', 'Companies', 'Users', 'Status', 'Created', '']);
    const acme = [...rowOf('Acme').querySelectorAll('td')].map((td) => td.textContent);
    expect(acme.slice(0, 5)).toEqual(['Acme', 'Several companies', '3', 'Active', '01 Sept 2026']);
    const beta = [...rowOf('Beta Ltd').querySelectorAll('td')].map((td) => td.textContent);
    expect(beta.slice(0, 4)).toEqual(['Beta Ltd', 'One company', '0', 'Disabled']);
    expect(rowActionLabels('Acme')).toEqual(['Enter', 'Users', 'Open', 'Rename', 'Disable']);
    expect(rowActionLabels('Beta Ltd')).toEqual(['Enter', 'Users', 'Open', 'Rename', 'Enable']);
  });

  it('creates an organization from the dialog, several companies by default, and shows a refusal in .msg', async () => {
    const stub = await openPortal();
    fireEvent.click(screen.getByRole('button', { name: '+ Create an organization' }));
    expect(dialogTitle()).toBe('Create an organization');
    const select = document.getElementById('orgMode') as HTMLSelectElement;
    expect(select.value).toBe('multiple');
    expect([...select.options].map((o) => o.textContent)).toEqual(['Several companies', 'One company']);
    stub.on('POST /admin/organizations', problem(409, 'duplicate_organization', 'An organization named Acme already exists'));
    fireEvent.change(input('orgName'), { target: { value: 'Acme' } });
    fireEvent.click(footerButton('Create'));
    await flush();
    expect(dialogMsg()?.textContent).toBe('An organization named Acme already exists');
    expect(dialogTitle()).toBe('Create an organization');

    stub.on('POST /admin/organizations', json(201, org({ id: 'org-3', name: 'Gamma', slug: 'gamma', companyMode: 'single' })));
    stub.on('GET /admin/organizations', paged([...ORGS, org({ id: 'org-3', name: 'Gamma', slug: 'gamma', companyMode: 'single', users: 0 })]));
    fireEvent.change(input('orgName'), { target: { value: 'Gamma' } });
    fireEvent.change(select, { target: { value: 'single' } });
    fireEvent.click(footerButton('Create'));
    await flush();
    const call = stub.to('POST /admin/organizations')[1];
    expect(call.body).toEqual({ name: 'Gamma', companyMode: 'single' });
    expect(call.headers['x-csrf-token']).toBe(CSRF);
    expect(document.querySelector('.dlg')).toBeNull();
    expect(rowOf('Gamma')).not.toBeNull();
  });

  it('renames from its dialog and edits the company mode from the row', async () => {
    const stub = await openPortal();
    stub.on('PATCH /admin/organizations/org-1', json(200, org({ name: 'Acme Group' })));
    fireEvent.click(rowAction('Acme', 'Rename'));
    expect(dialogTitle()).toBe('Rename Acme');
    fireEvent.change(input('orgRename'), { target: { value: 'Acme Group' } });
    fireEvent.click(footerButton('Rename'));
    await flush();
    expect(stub.to('PATCH /admin/organizations/org-1')[0].body).toEqual({ name: 'Acme Group' });

    fireEvent.click(screen.getByText('Acme'));
    expect(dialogTitle()).toBe('Edit Acme');
    const select = document.getElementById('orgEditMode') as HTMLSelectElement;
    expect(select.value).toBe('multiple');
    fireEvent.change(select, { target: { value: 'single' } });
    fireEvent.click(footerButton('Save'));
    await flush();
    expect(stub.to('PATCH /admin/organizations/org-1')[1].body).toEqual({ companyMode: 'single' });
  });

  it('asks before disabling, with the danger button and the exact body', async () => {
    const stub = await openPortal();
    stub.on('POST /admin/organizations/org-1/disable', json(200, org({ status: 'disabled' })));
    fireEvent.click(rowAction('Acme', 'Disable'));
    expect(dialogTitle()).toBe('Disable Acme?');
    expect(topDialog().querySelector('.db')?.textContent).toBe('Every user of Acme is signed out and can no longer sign in. Its data is kept.');
    const disable = footerButton('Disable');
    expect(disable.className).toContain('danger');
    expect(stub.to('POST /admin/organizations/org-1/disable')).toHaveLength(0);
    fireEvent.click(disable);
    await flush();
    expect(stub.to('POST /admin/organizations/org-1/disable')).toHaveLength(1);
  });

  it('shows the platform audit log with its six columns and ok or refused', async () => {
    await openPortal();
    fireEvent.click(screen.getByRole('button', { name: 'Platform audit log' }));
    await flush();
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('Platform audit log');
    expect([...document.querySelectorAll('.tbl th')].map((th) => th.textContent)).toEqual(['When', 'Who', 'Action', 'Organization', 'What', 'Result']);
    const created = [...rowOf('Created the organization Acme').querySelectorAll('td')].map((td) => td.textContent);
    expect(created.slice(1)).toEqual(['admin@platform.example', 'organization_created', 'Acme', 'Created the organization Acme', 'ok']);
    const failed = [...rowOf('A sign-in with an unknown email failed').querySelectorAll('td')].map((td) => td.textContent);
    expect(failed.slice(1)).toEqual(['—', 'sign_in_failed', '—', 'A sign-in with an unknown email failed', 'refused']);
  });
});

describe('the users of an organization', () => {
  it('maps the status texts', () => {
    expect(userStatus(user())).toBe('Active');
    expect(userStatus(user({ status: 'disabled', locked: true }))).toBe('Disabled');
    expect(userStatus(user({ locked: true, mustChangePassword: true }))).toBe('Locked');
    expect(userStatus(user({ mustChangePassword: true }))).toBe('Must change password');
  });

  it('lists them with groups and status and the row actions', async () => {
    await openUsers();
    const dlg = topDialog();
    expect(dlg.classList.contains('lg')).toBe(true);
    expect([...dlg.querySelectorAll('.tbl th')].map((th) => th.textContent)).toEqual(['Name', 'Email', 'Groups', 'Status', '']);
    expect([...rowOf('Ana').querySelectorAll('td')].slice(0, 4).map((td) => td.textContent)).toEqual(['Ana', 'ana@acme.example', 'Administrators', 'Active']);
    expect([...rowOf('Bo').querySelectorAll('td')].slice(2, 4).map((td) => td.textContent)).toEqual(['—', 'Disabled']);
    expect([...rowOf('Cy').querySelectorAll('td')][3].textContent).toBe('Must change password');
    expect(rowActionLabels('Ana')).toEqual(['Edit', 'Reset password', 'Disable']);
    expect(rowActionLabels('Bo')).toEqual(['Edit', 'Reset password', 'Enable']);
    expect(footerButton('+ Add a user')).toBeInTheDocument();
  });

  it('adds a user with an initial password and the groups ticked, then clears the password', async () => {
    const stub = await openUsers();
    fireEvent.click(footerButton('+ Add a user'));
    await flush();
    expect(dialogTitle()).toBe('Add a user');
    const dlg = topDialog();
    expect([...dlg.querySelectorAll('.form > label')].map((l) => l.textContent)).toEqual(['Name', 'Email', 'Department (optional)', 'Initial password', 'Groups']);
    expect(input('auPassword').type).toBe('password');
    expect(input('auPassword').autocomplete).toBe('new-password');
    expect(dialogMsg()?.textContent).toBe(ADD_USER_NOTE);
    const checks = dlg.querySelectorAll<HTMLInputElement>('.chk input[type=checkbox]');
    expect([...dlg.querySelectorAll('.chk b')].map((b) => b.textContent)).toEqual(['Administrators', 'Builders']);
    fireEvent.click(checks[1]);
    fireEvent.change(input('auName'), { target: { value: 'Dee' } });
    fireEvent.change(input('auEmail'), { target: { value: 'dee@acme.example' } });
    fireEvent.change(input('auPassword'), { target: { value: fresh(4) } });

    stub.on('POST /admin/organizations/org-1/users', problem(422, 'password_rejected', 'This password is too common. Choose another.'));
    fireEvent.click(footerButton('Add user'));
    await flush();
    expect(dialogMsg()?.textContent).toBe('This password is too common. Choose another.');
    expect(input('auPassword').value).toBe('');
    expect(input('auName').value).toBe('Dee');

    fireEvent.change(input('auPassword'), { target: { value: fresh(5) } });
    stub.on('POST /admin/organizations/org-1/users', json(201, user({ id: 'u-4', name: 'Dee', email: 'dee@acme.example', groups: [{ id: 'g-2', name: 'Builders' }] })));
    stub.on('GET /admin/organizations/org-1/users', paged([...USERS, user({ id: 'u-4', name: 'Dee', email: 'dee@acme.example', groups: [{ id: 'g-2', name: 'Builders' }] })]));
    fireEvent.click(footerButton('Add user'));
    await flush();
    const calls = stub.to('POST /admin/organizations/org-1/users');
    expect(calls[1].body).toEqual({ name: 'Dee', email: 'dee@acme.example', department: null, password: fresh(5), groupIds: ['g-2'] });
    expect(dialogTitle()).toBe('Users of Acme');
    expect(rowOf('Dee')).not.toBeNull();
  });

  it('resets a password from its dialog with the note', async () => {
    const stub = await openUsers();
    stub.on('PUT /admin/organizations/org-1/users/u-1/password', noContent());
    fireEvent.click(rowAction('Ana', 'Reset password'));
    expect(dialogTitle()).toBe('Reset password for Ana');
    expect(screen.getByLabelText('New password')).toBe(input('rpPassword'));
    expect(input('rpPassword').autocomplete).toBe('new-password');
    expect(dialogMsg()?.textContent).toBe(RESET_NOTE);
    fireEvent.change(input('rpPassword'), { target: { value: fresh(6) } });
    fireEvent.click(footerButton('Reset password'));
    await flush();
    const [call] = stub.to('PUT /admin/organizations/org-1/users/u-1/password');
    expect(call.body).toEqual({ newPassword: fresh(6) });
    expect(call.headers['x-csrf-token']).toBe(CSRF);
    expect(dialogTitle()).toBe('Users of Acme');
  });

  it('edits the name, department and groups', async () => {
    const stub = await openUsers();
    stub.on('PATCH /admin/organizations/org-1/users/u-1', json(200, user({ name: 'Ana B' })));
    fireEvent.click(rowAction('Ana', 'Edit'));
    await flush();
    expect(dialogTitle()).toBe('Edit Ana');
    const checks = topDialog().querySelectorAll<HTMLInputElement>('.chk input[type=checkbox]');
    expect([...checks].map((c) => c.checked)).toEqual([true, false]);
    fireEvent.click(checks[0]);
    fireEvent.click(checks[1]);
    fireEvent.change(input('euName'), { target: { value: 'Ana B' } });
    fireEvent.click(footerButton('Save'));
    await flush();
    expect(stub.to('PATCH /admin/organizations/org-1/users/u-1')[0].body).toEqual({ name: 'Ana B', department: 'Sales', groupIds: ['g-2'] });
  });

  it('asks before disabling a user', async () => {
    const stub = await openUsers();
    stub.on('POST /admin/organizations/org-1/users/u-1/disable', json(200, user({ status: 'disabled' })));
    fireEvent.click(rowAction('Ana', 'Disable'));
    expect(dialogTitle()).toBe('Disable Ana?');
    expect(topDialog().querySelector('.db')?.textContent).toBe('They are signed out and can no longer sign in.');
    expect(footerButton('Disable').className).toContain('danger');
    fireEvent.click(footerButton('Disable'));
    await flush();
    expect(stub.to('POST /admin/organizations/org-1/users/u-1/disable')).toHaveLength(1);
  });
});

describe('entering an organization', () => {
  it('asks first, then opens the Studio with the banner and Exit, which returns to the portal', async () => {
    const stub = await openPortal();
    const acting = actingSession('org-1', 'Acme');
    stub.on('POST /admin/organizations/org-1/enter', json(200, acting));
    fireEvent.click(rowAction('Acme', 'Enter'));
    expect(dialogTitle()).toBe('Enter Acme?');
    expect(topDialog().textContent).toContain('You act inside Acme with every role, as platform super admin. Everything you do there is recorded in its audit log.');
    fireEvent.click(footerButton('Enter'));
    await flush();
    expect(stub.to('POST /admin/organizations/org-1/enter')[0].headers['x-csrf-token']).toBe(CSRF);
    expect(auth.state.mode).toBe('studio');
    expect(auth.state.session?.acting?.organization.name).toBe('Acme');

    cleanup();
    render(
      <>
        <Header />
        <PlatformAccessBanner />
      </>,
    );
    const banner = document.getElementById('platformAccess') as HTMLElement;
    expect(banner.querySelector('span')?.textContent).toBe(actingText('Acme', 60));
    expect(banner.textContent).toBe('Acting in Acme as platform super admin · 60 min leftExit');
    expect((document.getElementById('status') as HTMLElement).classList.contains('on')).toBe(false);
    stub.on('POST /admin/exit', json(200, platformSession()));
    fireEvent.click(screen.getByRole('button', { name: 'Exit' }));
    await flush();
    expect(stub.to('POST /admin/exit')[0].headers['x-csrf-token']).toBe(acting.csrfToken);
    expect(auth.state.mode).toBe('platform');
    expect(document.getElementById('platformAccess')).toBeNull();
  });

  it('shows a refusal as a toast and stays in the portal', async () => {
    const stub = await openPortal();
    stub.on('POST /admin/organizations/org-2/enter', problem(409, 'organization_disabled', 'The organization is disabled; enable it first'));
    fireEvent.click(rowAction('Beta Ltd', 'Enter'));
    fireEvent.click(footerButton('Enter'));
    await flush();
    expect(auth.state.mode).toBe('platform');
    expect(store.ui.toasts.map((t) => t.text)).toContain('The organization is disabled; enable it first');
  });

  it('counts the minutes left and reads the session again once the hour has ended', async () => {
    expect(minutesLeft(new Date(1_000_000 + 61_000).toISOString(), 1_000_000)).toBe(2);
    expect(minutesLeft(new Date(1_000_000 - 5).toISOString(), 1_000_000)).toBe(0);
    const stub = await openPortal();
    stub.on('GET /auth/session', json(200, platformSession()));
    store.ui.status = 'ready';
    stub.on('GET /scene', json(200, sceneOf('Acme Co')));
    auth.replaceSession(actingSession('org-1', 'Acme', { acting: { organization: { id: 'org-1', name: 'Acme', slug: 'acme' }, since: new Date(Date.now() - 3_600_000).toISOString(), until: new Date(Date.now() - 1_000).toISOString() } }));
    await flush();
    cleanup();
    render(<PlatformAccessBanner />);
    await flush();
    expect(stub.to('GET /auth/session').length).toBe(2);
    expect(auth.state.mode).toBe('platform');
    expect(document.getElementById('platformAccess')).toBeNull();
    store.ui.status = 'loading';
  });

  it('drops the scene of the organization left when its answer lands after the next one', async () => {
    const stub = await openPortal();
    let releaseAlpha: (res: Response) => void = () => undefined;
    const slowAlpha = new Promise<Response>((resolve) => {
      releaseAlpha = resolve;
    });
    stub.on('GET /scene', () => slowAlpha);
    stub.on('POST /admin/exit', json(200, platformSession()));
    store.ui.status = 'ready';
    auth.replaceSession(actingSession('org-1', 'Acme'));
    await flush();
    expect(auth.state.mode).toBe('studio');
    await auth.exitOrganization();
    expect(auth.state.mode).toBe('platform');
    expect(store.s.companies).toEqual([]);
    stub.on('GET /scene', json(200, sceneOf('Beta Co')));
    auth.replaceSession(actingSession('org-2', 'Beta Ltd'));
    await flush();
    expect(store.s.companies.map((c) => c.name)).toEqual(['Beta Co']);
    releaseAlpha(json(200, sceneOf('Alpha Co')));
    await flush();
    await flush();
    expect(store.s.companies.map((c) => c.name)).toEqual(['Beta Co']);
    await auth.exitOrganization();
    store.ui.status = 'loading';
  });

  it('marks the audit log entries written through platform access', () => {
    directory.audit = [
      { id: 2, at: '2026-09-30T09:05:00Z', actor: { kind: 'user', id: 'u-9', name: 'Admin', platformAccountId: 'acc-sa' }, kind: 'concept', what: 'Approved Boiler', ok: true, origin: null, companyIds: [] },
      { id: 1, at: '2026-09-30T09:00:00Z', actor: { kind: 'user', id: 'u-1', name: 'Ana' }, kind: 'concept', what: 'Approved Pump', ok: true, origin: null, companyIds: [] },
    ];
    render(<AuditLog />);
    const rows = Array.from(document.querySelectorAll('.log > div')).map((row) => row.children[2].textContent);
    expect(rows).toEqual(['Approved Boiler · platform super admin', 'Approved Pump']);
    directory.audit = [];
  });
});

describe('a support session', () => {
  it('opens from the Open dialog into the Studio with the pill and End support, then returns to the portal', async () => {
    const stub = await openPortal();
    const support = platformSession({
      csrfToken: 'support-csrf-'.padEnd(43, 'z'),
      support: { organization: { id: 'org-1', name: 'Acme', slug: 'acme' }, until: '2026-09-30T10:00:00Z', reason: 'Ticket 12' },
    });
    stub.on('POST /admin/organizations/org-1/support-session', json(200, support));
    fireEvent.click(rowAction('Acme', 'Open'));
    expect(dialogTitle()).toBe('Open Acme');
    expect(topDialog().querySelector('.dh span')?.textContent).toBe('A read-only support session for 60 minutes, recorded in its audit log');
    fireEvent.change(input('supportReason'), { target: { value: 'Ticket 12' } });
    fireEvent.click(footerButton('Open'));
    await flush();
    expect(stub.to('POST /admin/organizations/org-1/support-session')[0].body).toEqual({ reason: 'Ticket 12' });
    expect(auth.state.mode).toBe('studio');
    expect(auth.state.session?.support?.organization.name).toBe('Acme');

    cleanup();
    render(
      <>
        <Header />
        <AccountControls />
      </>,
    );
    const pill = document.getElementById('status') as HTMLElement;
    expect(pill.classList.contains('on')).toBe(true);
    expect(pill.querySelector('span')?.textContent).toBe('Support · Acme · read-only');
    stub.on('DELETE /admin/support-session', json(200, platformSession()));
    fireEvent.click(screen.getByRole('button', { name: 'End support' }));
    await flush();
    expect(stub.to('DELETE /admin/support-session')[0].headers['x-csrf-token']).toBe(support.csrfToken);
    expect(auth.state.mode).toBe('platform');
  });
});
