/**
 * The client-side checks of a new password and the texts of every password refusal. The policy
 * itself lives in the API; the client only catches a mismatch and a short password before the call.
 */
import { ApiError } from '../api/types';
import { t } from '../i18n/i18n';
import { lockedText, unavailable } from './authStore';

export const MIN_PASSWORD_LENGTH = 12;

export const mismatch = (): string => t('auth.password.mismatch');
export const currentIncorrect = (): string => t('auth.password.currentIncorrect');
export const tooShort = (): string => t('auth.password.tooShort');
export const tooCommon = (): string => t('auth.password.tooCommon');
export const sameAsCurrent = (): string => t('auth.password.sameAsCurrent');
export const containsEmail = (): string => t('auth.password.containsEmail');
export const passwordHint = (): string => t('auth.password.hint');

/** The message for a new password that fails before the call, or null when it may be sent. */
export function newPasswordProblem(next: string, confirm: string): string | null {
  if (next !== confirm) return mismatch();
  if ([...next.normalize('NFC')].length < MIN_PASSWORD_LENGTH) return tooShort();
  return null;
}

/** The message for a refused password change or reset. */
export function passwordErrorText(err: unknown): string {
  if (!(err instanceof ApiError)) return unavailable();
  const { code, detail, title } = err.problem;
  if (code === 'current_password_incorrect') return currentIncorrect();
  if (code === 'password_rejected') return rejectedText(detail || '', title);
  if (err.status === 429) return lockedText(err.retryAfter);
  if (err.status >= 500) return unavailable();
  return detail || title;
}

/** The exact refusal text for a `password_rejected` detail, matched by its rule when it is phrased otherwise. */
function rejectedText(detail: string, title: string): string {
  for (const text of [tooShort(), tooCommon(), sameAsCurrent(), containsEmail()]) if (detail === text) return text;
  const lower = detail.toLowerCase();
  if (lower.includes('common') || lower.includes('breach')) return tooCommon();
  if (lower.includes('different') || lower.includes('same') || lower.includes('current')) return sameAsCurrent();
  if (lower.includes('email')) return containsEmail();
  if (lower.includes('12') || lower.includes('short') || lower.includes('length')) return tooShort();
  return detail || title;
}
