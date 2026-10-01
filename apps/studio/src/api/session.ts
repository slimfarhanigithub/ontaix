/**
 * What the client remembers of the browser session: the CSRF token every unsafe call carries,
 * and the two signals a call can raise about the session. The cookie itself is `HttpOnly`, so
 * nothing here ever holds a credential.
 *
 * `ended`: a call other than sign-in and the session read answered `401`, so the session is
 * over. `passwordChangeRequired`: a call answered `403 password_change_required`, so only the
 * password change is reachable until it is done.
 */
import type { Session } from './types';

export type AuthSignal = 'ended' | 'passwordChangeRequired';

type Listener = (signal: AuthSignal) => void;

let csrfToken: string | null = null;
const listeners = new Set<Listener>();

/** Keeps the CSRF token of the session a response returned. */
export function rememberSession(session: Session): Session {
  csrfToken = session.csrfToken;
  return session;
}

/** Drops the CSRF token; after sign-out, or once the session is known to have ended. */
export function forgetSession(): void {
  csrfToken = null;
}

/** The CSRF token of the live session, or null without one. */
export function currentCsrfToken(): string | null {
  return csrfToken;
}

export const authSignals = {
  subscribe(fn: Listener): () => void {
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  },
  emit(signal: AuthSignal): void {
    if (signal === 'ended') csrfToken = null;
    for (const fn of [...listeners]) fn(signal);
  },
};
