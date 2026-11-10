/**
 * The "Choose an organization" page, shown while a member session of an account with several
 * organizations names none: the same card as the sign-in page, one button per organization,
 * and a `Sign out` link-button on the left of the footer. Picking one binds the session to it
 * and opens the Studio; a refusal shows in the `.msg` in the conflict colour and the list stays.
 */
import { useState } from 'react';

import { t, useT } from '../i18n/i18n';
import { useBusyAction } from '../shell/busy';
import { auth, noOrganization, useAuth } from './authStore';
import { AuthPage, FormMessage } from './AuthPage';

export const chooseOrganizationNote = (): string => t('auth.chooseOrganization.note');

export function ChooseOrganization() {
  const t = useT();
  const { session } = useAuth();
  const [error, setError] = useState('');
  const [chosen, setChosen] = useState<string | null>(null);
  const { shown, run } = useBusyAction();
  const organizations = [...(session?.organizations ?? [])].sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }));
  const none = organizations.length === 0;
  const message = error || (none ? noOrganization() : chooseOrganizationNote());
  const pick = (id: string) =>
    void run(async () => {
      setChosen(id);
      setError('');
      const failure = await auth.chooseOrganization(id);
      if (!failure) return;
      setError(failure);
      setChosen(null);
    });
  return (
    <AuthPage
      title={t('auth.chooseOrganization.title')}
      sub={t('auth.chooseOrganization.sub')}
      onSubmit={() => undefined}
      footer={
        <button className="btn left" type="button" onClick={() => void auth.signOut()}>
          {t('auth.account.signOut')}
        </button>
      }
    >
      <div className="form" style={{ gridTemplateColumns: '1fr' }}>
        <div id="orgChoice" role="group" aria-label={t('auth.chooseOrganization.organizations')} style={{ display: 'grid', gap: '8px' }}>
          {organizations.map((o) => {
            const waiting = shown && chosen === o.id;
            return (
              <button
                key={o.id}
                type="button"
                className="btn"
                data-org={o.id}
                disabled={shown}
                aria-busy={waiting ? 'true' : undefined}
                style={{ textAlign: 'left', padding: '10px 12px', fontSize: '13px', color: 'var(--ink)' }}
                onClick={() => pick(o.id)}
              >
                {waiting ? <span className="spin"></span> : null}
                {o.name}
              </button>
            );
          })}
        </div>
        <FormMessage text={message} error={!!error || none} />
      </div>
    </AuthPage>
  );
}
