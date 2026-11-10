/**
 * The sign-in page: email and password, nothing else. No sign-up, no "remember me", no recovery
 * link. The `.msg` under the form holds the note, or the notice after a sign-out or an ended
 * session, or the error of the last attempt in the conflict colour. After every failure the
 * password is cleared and the focus returns to it.
 */
import { useRef, useState } from 'react';

import { t, useT } from '../i18n/i18n';
import { useBusyAction } from '../shell/busy';
import { auth, useAuth } from './authStore';
import { AuthPage, FormMessage } from './AuthPage';

export const signInNote = (): string => t('auth.signIn.note');

export function SignIn() {
  const t = useT();
  const { notice, error: bootError } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const passwordField = useRef<HTMLInputElement>(null);
  const { shown, run } = useBusyAction();
  const message = error || bootError || notice || signInNote();
  const submit = () =>
    void run(async () => {
      const failure = await auth.signIn(email.trim(), password);
      if (!failure) return;
      setError(failure);
      setPassword('');
      passwordField.current?.focus();
    });
  return (
    <AuthPage
      title={t('auth.signIn.title')}
      sub={t('auth.signIn.sub')}
      onSubmit={submit}
      footer={
        <button className="btn primary" type="submit" disabled={shown} aria-busy={shown ? 'true' : undefined}>
          {shown ? <span className="spin"></span> : null}
          {t('auth.signIn.title')}
        </button>
      }
    >
      <div className="form">
        <label htmlFor="siEmail">{t('auth.signIn.email')}</label>
        <input id="siEmail" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
        <label htmlFor="siPassword">{t('auth.signIn.password')}</label>
        <input
          id="siPassword"
          ref={passwordField}
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <FormMessage text={message} error={!!(error || bootError)} />
      </div>
    </AuthPage>
  );
}
