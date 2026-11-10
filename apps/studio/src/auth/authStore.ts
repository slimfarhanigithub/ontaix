/**
 * Which screen the Studio shows for the browser's session, and the moves between them: the
 * sign-in page, the "Choose a new password" page, the "Choose an organization" page (a member of
 * several organizations, before one is chosen), the Studio (a member, or a super admin inside
 * an organization he entered or inside a read-only support session) and the platform portal (a
 * super admin at home). The gate runs
 * only against a real API; the in-browser mock has no sessions.
 */
import { useSyncExternalStore } from 'react';

import { resetDirectory } from '../admin/adminData';
import { api, hasDevIdentity } from '../api/client';
import { authSignals, forgetSession } from '../api/session';
import { ApiError, type PortalLanguage, type Session } from '../api/types';
import { t } from '../i18n/i18n';
import { applyLanguage, resolveLanguage } from '../i18n/language';
import { store } from '../store/store';

export type AuthMode = 'loading' | 'signIn' | 'password' | 'organization' | 'studio' | 'platform';

export const signedOut = (): string => t('auth.notice.signedOut');
export const sessionEnded = (): string => t('auth.notice.sessionEnded');
export const incorrect = (): string => t('auth.error.incorrect');
export const unavailable = (): string => t('auth.error.unavailable');
export const noOrganization = (): string => t('auth.error.noOrganization');
/**
 * What a session shows of: the account and the organization it acts in, entered or looks at; a
 * change drops the previous data.
 */
const sessionKey = (s: Session | null): string =>
  s ? `${s.account.id}:${s.organization?.id ?? ''}:${s.acting?.organization.id ?? ''}:${s.support?.organization.id ?? ''}` : '';

/** The lock lasts 15 minutes; used when a `429` carries no `Retry-After`. */
const LOCK_MINUTES = 15;

export interface AuthState {
  mode: AuthMode;
  /** The live session; null on the sign-in page and for a development identity header. */
  session: Session | null;
  /** What the sign-in page's `.msg` says instead of its note: after sign-out or an ended session. */
  notice: string;
  /** What the sign-in page's `.msg` says when the session read itself failed. */
  error: string;
}

type Listener = () => void;

/** `Too many attempts. Try again in <n> minutes.`, `in 1 minute.` for one, from `Retry-After` rounded up. */
export function lockedText(retryAfterSeconds: number | null): string {
  const minutes = retryAfterSeconds === null ? LOCK_MINUTES : Math.max(1, Math.ceil(retryAfterSeconds / 60));
  return t('auth.error.locked', { n: minutes });
}

/** The sign-in page's message for a failed `POST /auth/sign-in`. */
export function signInErrorText(err: unknown): string {
  if (!(err instanceof ApiError)) return unavailable();
  if (err.status === 401) return incorrect();
  if (err.status === 403 && err.problem.code === 'no_organization') return noOrganization();
  if (err.status === 429) return lockedText(err.retryAfter);
  if (err.status >= 500) return unavailable();
  return err.problem.detail || err.problem.title;
}

/** The "Choose an organization" page's message for a failed `PUT /auth/session/organization`. */
export function chooseErrorText(err: unknown): string {
  if (!(err instanceof ApiError) || err.status >= 500) return unavailable();
  return err.problem.detail || err.problem.title;
}

class AuthStore {
  readonly state: AuthState = { mode: 'loading', session: null, notice: '', error: '' };
  private version = 0;
  private listeners = new Set<Listener>();
  private started = false;

  subscribe = (fn: Listener): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  getVersion = (): number => this.version;

  private bump(): void {
    this.version++;
    for (const fn of this.listeners) fn();
  }

  /** Reads the session once at start-up and listens for the signals a later call may raise. */
  async boot(): Promise<void> {
    if (!this.started) {
      this.started = true;
      authSignals.subscribe((signal) => {
        if (signal === 'ended') this.ended();
        else this.requirePasswordChange();
      });
    }
    try {
      this.enter(await api.getSession());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        if (hasDevIdentity()) this.show('studio', null);
        else this.show('signIn', null);
        return;
      }
      this.state.error = unavailable();
      this.show('signIn', null);
    }
  }

  /** Signs in; hands back the message to show, or null once the session is open. */
  async signIn(email: string, password: string): Promise<string | null> {
    try {
      this.enter(await api.signIn({ email, password }));
      return null;
    } catch (err) {
      return signInErrorText(err);
    }
  }

  /** Ends the session and returns to the sign-in page, whatever the API answered. */
  async signOut(): Promise<void> {
    try {
      await api.signOut();
    } catch {
      forgetSession();
    }
    this.state.notice = signedOut();
    this.show('signIn', null);
  }

  /**
   * Binds the member session to one of its organizations and opens the Studio in it; hands back
   * the message to show when the API refused, or null.
   */
  async chooseOrganization(organizationId: string): Promise<string | null> {
    try {
      this.enter(await api.chooseOrganization({ organizationId }));
      return null;
    } catch (err) {
      return chooseErrorText(err);
    }
  }

  /**
   * Returns a member of several organizations to the "Choose an organization" page. The
   * organization's data is dropped at once; the session stays bound to it on the server until
   * the next choice rotates the token.
   */
  switchOrganization(): void {
    const session = this.state.session;
    if (!session || session.kind !== 'member') return;
    this.show('organization', { ...session, organization: null, userId: null });
  }

  /** A password change, a support session's start or an organization entered replaced the session with the one the API returned. */
  replaceSession(session: Session): void {
    this.enter(session);
  }

  /**
   * Makes `language` the account's portal language: the Studio switches at once, the choice is
   * saved on the session and remembered in this browser; a refused save keeps the switch.
   */
  async chooseLanguage(language: PortalLanguage): Promise<void> {
    applyLanguage(language);
    const session = await api.chooseLanguage({ language });
    if (this.state.session && this.state.session.account.id === session.account.id) {
      this.state.session = { ...this.state.session, account: session.account };
      this.bump();
    }
  }

  /** Ends the super admin's support session; hands back the session without it. */
  async endSupport(): Promise<void> {
    this.enter(await api.endSupportSession());
  }

  /** Leaves the organization the super admin entered; hands back the session at the platform portal. */
  async exitOrganization(): Promise<void> {
    this.enter(await api.exitOrganization());
  }

  /** Reads the session again, after the hour of an entered organization ended on its own. */
  async refresh(): Promise<void> {
    try {
      this.enter(await api.getSession());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) this.ended();
    }
  }

  private enter(session: Session): void {
    if (session.mustChangePassword) this.show('password', session);
    else if (session.kind === 'platform' && !session.support && !session.acting) this.show('platform', session);
    else if (session.kind === 'member' && !session.organization) this.show('organization', session);
    else this.show('studio', session);
  }

  private ended(): void {
    if (this.state.mode === 'signIn' || this.state.mode === 'loading') return;
    this.state.notice = sessionEnded();
    this.show('signIn', null);
  }

  private requirePasswordChange(): void {
    if (!this.state.session || this.state.mode === 'password') return;
    this.show('password', { ...this.state.session, mustChangePassword: true });
  }

  private show(mode: AuthMode, session: Session | null): void {
    const leaving = this.state.mode;
    if (mode !== 'signIn') {
      this.state.notice = '';
      this.state.error = '';
    }
    if (sessionKey(session) !== sessionKey(this.state.session)) {
      store.nextSession();
      resetDirectory();
    }
    this.state.mode = mode;
    this.state.session = session;
    if (session) applyLanguage(resolveLanguage(session.account.language));
    if (mode !== 'studio' || leaving !== 'studio') {
      store.ui.adminOpen = false;
      store.ui.dialogs = [];
      store.bump();
    }
    // A Studio entered again, after another session or with an entered or support organization, starts from the server's scene.
    if (mode === 'studio' && leaving !== 'studio' && store.ui.status !== 'loading') void store.reloadScene();
    this.bump();
  }
}

export const auth = new AuthStore();

/** Re-renders the caller on every auth change and hands back the auth state. */
export function useAuth(): AuthState {
  useSyncExternalStore(auth.subscribe, auth.getVersion, auth.getVersion);
  return auth.state;
}
