import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

import { api } from '../api/client';
import { applyLanguage } from '../i18n/language';
import type { OrganizationRef } from '../api/types';
import { store } from '../store/store';
import { AccountControls } from './AccountControls';
import { auth, lockedText, noOrganization, sessionEnded, signedOut } from './authStore';
import { chooseOrganizationNote, ChooseOrganization } from './ChooseOrganization';
import { CSRF, json, noContent, platformSession, problem, session, stubFetch, type FetchStub } from './fetchStub';
import { Gate } from './Gate';
import { currentIncorrect, mismatch, passwordHint, tooCommon, tooShort } from './password';
import { signInNote } from './SignIn';

vi.mock('../App', () => ({ App: () => <div id="studio">Studio</div> }));
vi.mock('../platform/PlatformPortal', () => ({ PlatformPortal: () => <div id="platform">Platform</div> }));

// The gate renders whole pages, which jsdom lays out slowly under a full run.
vi.setConfig({ testTimeout: 30_000 });

const flush = () => act(() => new Promise((r) => setTimeout(r, 0)));
const msg = () => document.querySelector('.msg') as HTMLElement;
const input = (id: string) => document.getElementById(id) as HTMLInputElement;
const button = (label: string) => screen.getByRole('button', { name: label });

/** A fresh password that no fixture repeats, built at runtime. */
const fresh = (n: number) => `test-password-${n}-${'x'.repeat(8)}`;

async function open(stub: FetchStub): Promise<FetchStub> {
  render(<Gate />);
  await flush();
  return stub;
}

async function signIn(password = fresh(1)): Promise<void> {
  fireEvent.change(input('siEmail'), { target: { value: 'Ana@Acme.example' } });
  fireEvent.change(input('siPassword'), { target: { value: password } });
  fireEvent.submit(input('siPassword').closest('form') as HTMLFormElement);
  await flush();
}

beforeEach(() => {
  // Each test starts on a fresh session read.
  (auth as unknown as { state: { mode: string } }).state.mode = 'loading';
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  act(() => applyLanguage('en'));
  store.ui.dialogs = [];
  store.ui.toasts = [];
});

describe('lock text', () => {
  it('rounds Retry-After up to minutes and says minute for one', () => {
    expect(lockedText(300)).toBe('Too many attempts. Try again in 5 minutes.');
    expect(lockedText(61)).toBe('Too many attempts. Try again in 2 minutes.');
    expect(lockedText(60)).toBe('Too many attempts. Try again in 1 minute.');
    expect(lockedText(5)).toBe('Too many attempts. Try again in 1 minute.');
    expect(lockedText(null)).toBe('Too many attempts. Try again in 15 minutes.');
  });
});

describe('the sign-in page', () => {
  it('shows after a 401 session read, with the exact texts and no sign-up, recovery or remember me', async () => {
    await open(stubFetch({ 'GET /auth/session': problem(401, 'unauthorized', 'no session') }));
    expect(document.querySelector('.signin .wordmark')?.textContent).toBe('Ontology Builder business as a product');
    const card = document.querySelector('form.dlg.sm') as HTMLElement;
    expect(card.querySelector('.dh b')?.textContent).toBe('Sign in');
    expect(card.querySelector('.dh span')?.textContent).toBe('Use the account your administrator gave you');
    expect(card.querySelector('.dh .x')).toBeNull();
    expect(input('siEmail').type).toBe('email');
    expect(input('siEmail').autocomplete).toBe('username');
    expect(input('siPassword').type).toBe('password');
    expect(input('siPassword').autocomplete).toBe('current-password');
    expect(screen.getByLabelText('Email')).toBe(input('siEmail'));
    expect(screen.getByLabelText('Password')).toBe(input('siPassword'));
    expect(card.querySelector('.df .btn.primary')?.textContent).toBe('Sign in');
    expect(msg().textContent).toBe(signInNote());
    expect(document.querySelector('a')).toBeNull();
    expect(document.querySelector('input[type=checkbox]')).toBeNull();
    expect(document.querySelectorAll('input').length).toBe(2);
  });

  it('reads in French once the portal language is French, with the same ids and fields', async () => {
    await open(stubFetch({ 'GET /auth/session': problem(401, 'unauthorized', 'no session') }));
    act(() => applyLanguage('fr'));
    const card = document.querySelector('form.dlg.sm') as HTMLElement;
    expect(card.querySelector('.dh b')?.textContent).toBe('Se connecter');
    expect(card.querySelector('.dh span')?.textContent).toBe('Utilisez le compte que votre administrateur vous a donné');
    expect(screen.getByLabelText('E-mail')).toBe(input('siEmail'));
    expect(screen.getByLabelText('Mot de passe')).toBe(input('siPassword'));
    expect(card.querySelector('.df .btn.primary')?.textContent).toBe('Se connecter');
    expect(msg().textContent).toBe('Pas de compte ? Adressez-vous à votre administrateur. Mot de passe oublié ? Demandez à votre administrateur de le réinitialiser.');
    expect(lockedText(60)).toBe('Trop de tentatives. Réessayez dans 1 minute.');
    expect(lockedText(300)).toBe('Trop de tentatives. Réessayez dans 5 minutes.');
  });

  it('opens the Studio on success and remembers the CSRF token for unsafe calls only', async () => {
    const stub = await open(
      stubFetch({
        'GET /auth/session': problem(401, 'unauthorized', 'no session'),
        'POST /auth/sign-in': json(200, session()),
        'GET /scene': json(200, {}),
        'POST /proposals/p1/approve': json(200, {}),
      }),
    );
    await signIn();
    expect(document.getElementById('studio')).not.toBeNull();
    const [call] = stub.to('POST /auth/sign-in');
    expect(call.body).toEqual({ email: 'Ana@Acme.example', password: fresh(1) });
    expect(call.headers['x-csrf-token']).toBeUndefined();
    expect(call.headers['x-ontaix-user']).toBeUndefined();

    await api.approve('p1');
    await api.getScene().catch(() => undefined);
    expect(stub.to('POST /proposals/p1/approve')[0].headers['x-csrf-token']).toBe(CSRF);
    expect(stub.to('GET /scene')[0].headers['x-csrf-token']).toBeUndefined();
  });

  it('says the credentials are wrong on 401, clears the password and focuses it', async () => {
    await open(
      stubFetch({
        'GET /auth/session': problem(401, 'unauthorized', 'no session'),
        'POST /auth/sign-in': problem(401, 'invalid_credentials', 'Email or password is incorrect'),
      }),
    );
    await signIn();
    expect(msg().textContent).toBe('Email or password is incorrect.');
    expect(msg().style.color).toBe('var(--conflict)');
    expect(input('siPassword').value).toBe('');
    expect(input('siEmail').value).toBe('Ana@Acme.example');
    expect(document.activeElement).toBe(input('siPassword'));
  });

  it('says how long the lock lasts on 429, in minutes rounded up', async () => {
    const stub = await open(
      stubFetch({
        'GET /auth/session': problem(401, 'unauthorized', 'no session'),
        'POST /auth/sign-in': problem(429, 'sign_in_locked', 'locked', { 'Retry-After': '540' }),
      }),
    );
    await signIn();
    expect(msg().textContent).toBe('Too many attempts. Try again in 9 minutes.');
    stub.on('POST /auth/sign-in', problem(429, 'sign_in_locked', 'locked', { 'Retry-After': '30' }));
    await signIn();
    expect(msg().textContent).toBe('Too many attempts. Try again in 1 minute.');
    expect(input('siPassword').value).toBe('');
  });

  it('says sign-in is unavailable on a network failure or a 5xx', async () => {
    const stub = await open(
      stubFetch({
        'GET /auth/session': problem(401, 'unauthorized', 'no session'),
        'POST /auth/sign-in': new TypeError('Failed to fetch'),
      }),
    );
    await signIn();
    expect(msg().textContent).toBe('Sign-in is unavailable. Try again in a moment.');
    stub.on('POST /auth/sign-in', json(502, { title: 'Bad gateway' }));
    await signIn();
    expect(msg().textContent).toBe('Sign-in is unavailable. Try again in a moment.');
  });

  it('returns with the session-ended notice when a later call answers 401', async () => {
    await open(
      stubFetch({
        'GET /auth/session': json(200, session()),
        'GET /proposals': problem(401, 'unauthorized', 'session ended'),
      }),
    );
    expect(document.getElementById('studio')).not.toBeNull();
    await act(() => api.listProposals().catch(() => undefined));
    expect(document.getElementById('studio')).toBeNull();
    expect(msg().textContent).toBe(sessionEnded());
    expect(msg().style.color).toBe('');
  });

  it('goes to the platform portal for a super admin without a support session', async () => {
    await open(stubFetch({ 'GET /auth/session': json(200, platformSession()) }));
    expect(document.getElementById('platform')).not.toBeNull();
    expect(document.getElementById('studio')).toBeNull();
  });

  it('says the account belongs to no organization on 403 no_organization', async () => {
    await open(
      stubFetch({
        'GET /auth/session': problem(401, 'unauthorized', 'no session'),
        'POST /auth/sign-in': problem(403, 'no_organization', 'No membership'),
      }),
    );
    await signIn();
    expect(msg().textContent).toBe(noOrganization());
    expect(msg().style.color).toBe('var(--conflict)');
    expect(input('siPassword').value).toBe('');
  });
});

describe('Choose an organization', () => {
  const ACME: OrganizationRef = { id: 'org-1', name: 'Acme', slug: 'acme' };
  const BETA: OrganizationRef = { id: 'org-2', name: 'Beta Ltd', slug: 'beta' };
  /** A member of two organizations, none chosen yet. */
  const unchosen = (over = {}) => session({ organization: null, userId: null, organizations: [BETA, ACME], ...over });
  const choices = () => [...document.querySelectorAll<HTMLButtonElement>('#orgChoice button')];

  it('shows after sign-in for a member of several organizations, with the exact texts, and sign-out', async () => {
    const stub = await open(
      stubFetch({
        'GET /auth/session': problem(401, 'unauthorized', 'no session'),
        'POST /auth/sign-in': json(200, unchosen()),
        'POST /auth/sign-out': noContent(),
      }),
    );
    await signIn();
    expect(document.getElementById('studio')).toBeNull();
    const card = document.querySelector('form.dlg.sm') as HTMLElement;
    expect(card.querySelector('.dh b')?.textContent).toBe('Choose an organization');
    expect(card.querySelector('.dh span')?.textContent).toBe('Your account belongs to more than one');
    expect(card.querySelector('.dh .x')).toBeNull();
    const group = document.getElementById('orgChoice') as HTMLElement;
    expect(group.getAttribute('role')).toBe('group');
    expect(group.getAttribute('aria-label')).toBe('Organizations');
    expect(choices().map((b) => b.textContent)).toEqual(['Acme', 'Beta Ltd']);
    expect(choices().map((b) => b.dataset.org)).toEqual(['org-1', 'org-2']);
    for (const b of choices()) expect(b.type).toBe('button');
    expect(msg().textContent).toBe(chooseOrganizationNote());
    expect(msg().style.color).toBe('');
    expect(card.querySelector('.df .btn.left')?.textContent).toBe('Sign out');
    expect(card.querySelector('.df .btn.primary')).toBeNull();
    expect(document.querySelectorAll('input').length).toBe(0);

    fireEvent.click(button('Sign out'));
    await flush();
    expect(stub.to('POST /auth/sign-out')[0].headers['x-csrf-token']).toBe(CSRF);
    expect(document.querySelector('.dh b')?.textContent).toBe('Sign in');
    expect(msg().textContent).toBe(signedOut());
  });

  it('is the screen of a session read that names no organization yet', async () => {
    await open(stubFetch({ 'GET /auth/session': json(200, unchosen()) }));
    expect(document.querySelector('.dh b')?.textContent).toBe('Choose an organization');
    expect(auth.state.mode).toBe('organization');
  });

  it('enters the organization picked, sending the CSRF token, and uses the rotated token after', async () => {
    const stub = await open(stubFetch({ 'GET /auth/session': json(200, unchosen()) }));
    const next = session({ organization: BETA, organizations: [BETA, ACME], csrfToken: 'next-csrf-'.padEnd(43, 'y') });
    stub.on('PUT /auth/session/organization', json(200, next));
    stub.on('POST /proposals/p1/approve', json(200, {}));
    fireEvent.click(button('Beta Ltd'));
    await flush();
    const [call] = stub.to('PUT /auth/session/organization');
    expect(call.body).toEqual({ organizationId: 'org-2' });
    expect(call.headers['x-csrf-token']).toBe(CSRF);
    expect(document.getElementById('studio')).not.toBeNull();
    expect(auth.state.session?.organization?.name).toBe('Beta Ltd');
    await api.approve('p1');
    expect(stub.to('POST /proposals/p1/approve')[0].headers['x-csrf-token']).toBe(next.csrfToken);
  });

  it('keeps the list and shows the refusal in the conflict colour', async () => {
    const stub = await open(stubFetch({ 'GET /auth/session': json(200, unchosen()) }));
    stub.on('PUT /auth/session/organization', problem(409, 'organization_disabled', 'The organization is disabled'));
    fireEvent.click(button('Acme'));
    await flush();
    expect(document.querySelector('.dh b')?.textContent).toBe('Choose an organization');
    expect(msg().textContent).toBe('The organization is disabled');
    expect(msg().style.color).toBe('var(--conflict)');
    expect(choices().map((b) => b.disabled)).toEqual([false, false]);
    stub.on('PUT /auth/session/organization', new TypeError('Failed to fetch'));
    fireEvent.click(button('Acme'));
    await flush();
    expect(msg().textContent).toBe('Sign-in is unavailable. Try again in a moment.');
  });

  it('returns to the sign-in page with the notice when the choice answers 401', async () => {
    const stub = await open(stubFetch({ 'GET /auth/session': json(200, unchosen()) }));
    stub.on('PUT /auth/session/organization', problem(401, 'unauthorized', 'session ended'));
    fireEvent.click(button('Acme'));
    await flush();
    expect(document.querySelector('.dh b')?.textContent).toBe('Sign in');
    expect(msg().textContent).toBe(sessionEnded());
  });

  it('says the account belongs to no organization when the session lists none', async () => {
    await open(stubFetch({ 'GET /auth/session': json(200, unchosen({ organizations: [] })) }));
    expect(choices()).toEqual([]);
    expect(msg().textContent).toBe(noOrganization());
    expect(msg().style.color).toBe('var(--conflict)');
    expect(button('Sign out')).toBeInTheDocument();
  });

  it('comes after the forced password change', async () => {
    const stub = await open(stubFetch({ 'GET /auth/session': json(200, unchosen({ mustChangePassword: true })) }));
    expect(document.querySelector('.dh b')?.textContent).toBe('Choose a new password');
    stub.on('PUT /auth/password', json(200, unchosen()));
    fireEvent.change(input('cp-current'), { target: { value: fresh(1) } });
    fireEvent.change(input('cp-next'), { target: { value: fresh(2) } });
    fireEvent.change(input('cp-confirm'), { target: { value: fresh(2) } });
    fireEvent.submit(input('cp-next').closest('form') as HTMLFormElement);
    await flush();
    expect(document.querySelector('.dh b')?.textContent).toBe('Choose an organization');
  });

  it('enters directly with one organization, as before', async () => {
    await open(stubFetch({ 'GET /auth/session': json(200, session()) }));
    expect(document.getElementById('studio')).not.toBeNull();
    expect(auth.state.mode).toBe('studio');
  });

  it('offers Switch organization only to a member of several, and it returns to the choice dropping the data', async () => {
    await open(stubFetch({ 'GET /auth/session': json(200, session()) }));
    cleanup();
    render(<AccountControls />);
    expect([...document.querySelectorAll('#adminAccount .btn')].map((b) => b.textContent)).toEqual(['Language', 'Change password', 'Sign out']);
    cleanup();

    auth.replaceSession(session({ organization: BETA, organizations: [BETA, ACME] }));
    store.s.companies.push({ name: 'Beta Co' } as never);
    render(<AccountControls />);
    expect([...document.querySelectorAll('#adminAccount .btn')].map((b) => b.textContent)).toEqual(['Switch organization', 'Language', 'Change password', 'Sign out']);
    fireEvent.click(button('Switch organization'));
    expect(auth.state.mode).toBe('organization');
    expect(auth.state.session?.organization).toBeNull();
    expect(auth.state.session?.organizations).toEqual([BETA, ACME]);
    expect(store.s.companies).toEqual([]);
    cleanup();
    render(<ChooseOrganization />);
    expect(document.querySelector('.dh b')?.textContent).toBe('Choose an organization');
    expect(choices().map((b) => b.textContent)).toEqual(['Acme', 'Beta Ltd']);
  });

  it('never offers Switch organization to a platform account', async () => {
    await open(stubFetch({ 'GET /auth/session': json(200, platformSession()) }));
    cleanup();
    render(<AccountControls />);
    expect(document.getElementById('switchOrganization')).toBeNull();
  });
});

describe('Choose a new password', () => {
  const mustChange = () => stubFetch({ 'GET /auth/session': json(200, session({ mustChangePassword: true })) });

  async function save(current: string, next: string, confirm: string): Promise<void> {
    fireEvent.change(input('cp-current'), { target: { value: current } });
    fireEvent.change(input('cp-next'), { target: { value: next } });
    fireEvent.change(input('cp-confirm'), { target: { value: confirm } });
    fireEvent.submit(input('cp-next').closest('form') as HTMLFormElement);
    await flush();
  }

  it('is the only screen while mustChangePassword is true, with the exact texts', async () => {
    await open(mustChange());
    expect(document.getElementById('studio')).toBeNull();
    const card = document.querySelector('form.dlg.sm') as HTMLElement;
    expect(card.querySelector('.dh b')?.textContent).toBe('Choose a new password');
    expect(card.querySelector('.dh span')?.textContent).toBe('Your password was set by an administrator. Choose your own to continue.');
    expect(screen.getByLabelText('Current password').getAttribute('autocomplete')).toBe('current-password');
    expect(screen.getByLabelText('New password').getAttribute('autocomplete')).toBe('new-password');
    expect(screen.getByLabelText('Confirm new password').getAttribute('autocomplete')).toBe('new-password');
    for (const el of document.querySelectorAll('input')) expect(el.type).toBe('password');
    expect(msg().textContent).toBe(passwordHint());
    expect(card.querySelector('.df .btn.primary')?.textContent).toBe('Save password');
    expect(card.querySelector('.df .btn.left')?.textContent).toBe('Sign out');
  });

  it('checks the confirmation and the length before calling, clearing the fields', async () => {
    const stub = await open(mustChange());
    await save(fresh(1), fresh(2), fresh(3));
    expect(msg().textContent).toBe(mismatch());
    expect(stub.to('PUT /auth/password')).toHaveLength(0);
    expect(input('cp-next').value).toBe('');
    expect(input('cp-current').value).toBe('');
    await save(fresh(1), 'short-pw-11', 'short-pw-11');
    expect(msg().textContent).toBe(tooShort());
    expect(stub.to('PUT /auth/password')).toHaveLength(0);
  });

  it('maps the API refusals to the exact texts', async () => {
    const stub = await open(mustChange());
    stub.on('PUT /auth/password', problem(422, 'current_password_incorrect', 'The current password does not verify'));
    await save(fresh(1), fresh(2), fresh(2));
    expect(msg().textContent).toBe(currentIncorrect());
    stub.on('PUT /auth/password', problem(422, 'password_rejected', tooCommon()));
    await save(fresh(1), fresh(2), fresh(2));
    expect(msg().textContent).toBe(tooCommon());
    stub.on('PUT /auth/password', problem(422, 'password_rejected', 'It contains the local part of the email'));
    await save(fresh(1), fresh(2), fresh(2));
    expect(msg().textContent).toBe('The password must not contain your email name.');
    expect(input('cp-next').value).toBe('');
  });

  it('opens the Studio with the new session once saved, sending the CSRF token', async () => {
    const stub = await open(mustChange());
    const next = session({ csrfToken: 'next-csrf-'.padEnd(43, 'y') });
    stub.on('PUT /auth/password', json(200, next));
    stub.on('POST /proposals/p1/approve', json(200, {}));
    await save(fresh(1), fresh(2), fresh(2));
    const [call] = stub.to('PUT /auth/password');
    expect(call.body).toEqual({ currentPassword: fresh(1), newPassword: fresh(2) });
    expect(call.headers['x-csrf-token']).toBe(CSRF);
    expect(document.getElementById('studio')).not.toBeNull();
    await api.approve('p1');
    expect(stub.to('POST /proposals/p1/approve')[0].headers['x-csrf-token']).toBe(next.csrfToken);
  });

  it('is reached from the Studio when a call answers 403 password_change_required', async () => {
    await open(
      stubFetch({
        'GET /auth/session': json(200, session()),
        'GET /proposals': problem(403, 'password_change_required', 'Change your password first'),
      }),
    );
    expect(document.getElementById('studio')).not.toBeNull();
    await act(() => api.listProposals().catch(() => undefined));
    expect(document.getElementById('studio')).toBeNull();
    expect(document.querySelector('.dh b')?.textContent).toBe('Choose a new password');
  });

  it('signs out to the sign-in page, which says so', async () => {
    const stub = await open(mustChange());
    stub.on('POST /auth/sign-out', noContent());
    fireEvent.click(button('Sign out'));
    await flush();
    expect(stub.to('POST /auth/sign-out')[0].headers['x-csrf-token']).toBe(CSRF);
    expect(document.querySelector('.dh b')?.textContent).toBe('Sign in');
    expect(msg().textContent).toBe(signedOut());
  });
});
