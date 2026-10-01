/**
 * The three fields of a password change, `Current password`, `New password` and `Confirm new
 * password`, with the hint or the error under them, shared by the "Choose a new password" page
 * and the admin portal's Change password dialog. The values live in component state only, are
 * never logged or stored, and are cleared after every submit.
 */
import { useRef, useState, type RefObject } from 'react';

import { api } from '../api/client';
import type { Session } from '../api/types';
import { FormMessage } from './AuthPage';
import { newPasswordProblem, PASSWORD_HINT, passwordErrorText } from './password';

export interface PasswordDraft {
  current: string;
  next: string;
  confirm: string;
}

const EMPTY: PasswordDraft = { current: '', next: '', confirm: '' };

export interface PasswordChangeState {
  draft: PasswordDraft;
  setDraft: (draft: PasswordDraft) => void;
  error: string;
  first: RefObject<HTMLInputElement | null>;
  /** Checks, then calls `PUT /auth/password`; hands back the new session, or null with the error set. */
  save: () => Promise<Session | null>;
}

export function usePasswordChange(): PasswordChangeState {
  const [draft, setDraft] = useState<PasswordDraft>(EMPTY);
  const [error, setError] = useState('');
  const first = useRef<HTMLInputElement>(null);
  const fail = (message: string) => {
    setError(message);
    setDraft(EMPTY);
    first.current?.focus();
    return null;
  };
  const save = async (): Promise<Session | null> => {
    const problem = newPasswordProblem(draft.next, draft.confirm);
    if (problem) return fail(problem);
    try {
      const session = await api.changePassword({ currentPassword: draft.current, newPassword: draft.next });
      setError('');
      setDraft(EMPTY);
      return session;
    } catch (err) {
      return fail(passwordErrorText(err));
    }
  };
  return { draft, setDraft, error, first, save };
}

export function PasswordFields({ state, prefix }: { state: PasswordChangeState; prefix: string }) {
  const { draft, setDraft, error, first } = state;
  const field = (key: keyof PasswordDraft, label: string, autoComplete: string, ref?: RefObject<HTMLInputElement | null>) => (
    <>
      <label htmlFor={`${prefix}-${key}`}>{label}</label>
      <input
        id={`${prefix}-${key}`}
        ref={ref}
        type="password"
        autoComplete={autoComplete}
        value={draft[key]}
        onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
      />
    </>
  );
  return (
    <div className="form">
      {field('current', 'Current password', 'current-password', first)}
      {field('next', 'New password', 'new-password')}
      {field('confirm', 'Confirm new password', 'new-password')}
      <FormMessage text={error || PASSWORD_HINT} error={!!error} />
    </div>
  );
}
