/**
 * The client-side checks of a new password and the texts of every password refusal. The policy
 * itself lives in the API; the client only catches a mismatch and a short password before the call.
 */
import { ApiError } from '../api/types';
import { lockedText, UNAVAILABLE } from './authStore';

export const MIN_PASSWORD_LENGTH = 12;

export const MISMATCH = 'The passwords do not match.';
export const CURRENT_INCORRECT = 'Current password is incorrect.';
export const TOO_SHORT = 'Use at least 12 characters.';
export const TOO_COMMON = 'This password is too common. Choose another.';
export const SAME_AS_CURRENT = 'Choose a password different from the current one.';
export const CONTAINS_EMAIL = 'The password must not contain your email name.';
export const PASSWORD_HINT = 'At least 12 characters. Avoid common passwords.';

/** The message for a new password that fails before the call, or null when it may be sent. */
export function newPasswordProblem(next: string, confirm: string): string | null {
  if (next !== confirm) return MISMATCH;
  if ([...next.normalize('NFC')].length < MIN_PASSWORD_LENGTH) return TOO_SHORT;
  return null;
}

/** The message for a refused password change or reset. */
export function passwordErrorText(err: unknown): string {
  if (!(err instanceof ApiError)) return UNAVAILABLE;
  const { code, detail, title } = err.problem;
  if (code === 'current_password_incorrect') return CURRENT_INCORRECT;
  if (code === 'password_rejected') return rejectedText(detail || '', title);
  if (err.status === 429) return lockedText(err.retryAfter);
  if (err.status >= 500) return UNAVAILABLE;
  return detail || title;
}

/** The exact refusal text for a `password_rejected` detail, matched by its rule when it is phrased otherwise. */
function rejectedText(detail: string, title: string): string {
  for (const text of [TOO_SHORT, TOO_COMMON, SAME_AS_CURRENT, CONTAINS_EMAIL]) if (detail === text) return text;
  const lower = detail.toLowerCase();
  if (lower.includes('common') || lower.includes('breach')) return TOO_COMMON;
  if (lower.includes('different') || lower.includes('same') || lower.includes('current')) return SAME_AS_CURRENT;
  if (lower.includes('email')) return CONTAINS_EMAIL;
  if (lower.includes('12') || lower.includes('short') || lower.includes('length')) return TOO_SHORT;
  return detail || title;
}
