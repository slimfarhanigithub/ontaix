/**
 * Which screen the Studio shows for the browser's session, and the moves between them: the
 * sign-in page, the "Choose a new password" page, the Studio (a member, or a super admin inside
 * an organization he entered or inside a read-only support session) and the platform portal (a
 * super admin at home). The gate runs
 * only against a real API; the in-browser mock has no sessions.
 */
import { useSyncExternalStore } from 'react';

import { api, hasDevIdentity } from '../api/client';
import { authSignals, forgetSession } from '../api/session';
import { ApiError, type Session } from '../api/types';
import { store } from '../store/store';

export type AuthMode = 'loading' | 'signIn' | 'password' | 'studio' | 'platform';

export const SIGNED_OUT = 'You are signed out.';
export const SESSION_ENDED = 'Your session has ended. Sign in again.';
export const INCORRECT = 'Email or password is incorrect.';
export const UNAVAILABLE = 'Sign-in is unavailable. Try again in a moment.';
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
  return `Too many attempts. Try again in ${minutes} minute${minutes === 1 ? '' : 's'}.`;
}

/** The sign-in page's message for a failed `POST /auth/sign-in`. */
export function signInErrorText(err: unknown): string {
  if (!(err instanceof ApiError)) return UNAVAILABLE;
  if (err.status === 401) return INCORRECT;
  if (err.status === 429) return lockedText(err.retryAfter);
  if (err.status >= 500) return UNAVAILABLE;
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
      this.state.error = UNAVAILABLE;
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
    this.state.notice = SIGNED_OUT;
    this.show('signIn', null);
  }

  /** A password change, a support session's start or an organization entered replaced the session with the one the API returned. */
  replaceSession(session: Session): void {
    this.enter(session);
  }

  /** Ends the super admin's support session; hands back the session without it. */
  async endSupport(): Promise<void> {
    this.enter(await api.endSupportSession());
  }

  /** Leaves the organization the super admin entered; hands back the session at the platform portal. */
  async exitOrganization(): Promise<void> {
    this.enter(await api.exitOrganization());
  }

  private enter(session: Session): void {
    if (session.mustChangePassword) this.show('password', session);
    else if (session.kind === 'platform' && !session.support && !session.acting) this.show('platform', session);
    else this.show('studio', session);
  }

  private ended(): void {
    if (this.state.mode === 'signIn' || this.state.mode === 'loading') return;
    this.state.notice = SESSION_ENDED;
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
    this.state.mode = mode;
    this.state.session = session;
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
