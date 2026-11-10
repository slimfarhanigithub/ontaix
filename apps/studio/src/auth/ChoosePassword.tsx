/**
 * The "Choose a new password" page, shown while `mustChangePassword` is true and nothing else
 * is reachable: the same card as the sign-in page, the three password fields, `Save password`
 * and a `Sign out` link-button on the left of the footer.
 */
import { useT } from '../i18n/i18n';
import { useBusyAction } from '../shell/busy';
import { auth } from './authStore';
import { AuthPage } from './AuthPage';
import { PasswordFields, usePasswordChange } from './PasswordFields';

export function ChoosePassword() {
  const t = useT();
  const change = usePasswordChange();
  const { shown, run } = useBusyAction();
  const submit = () =>
    void run(async () => {
      const session = await change.save();
      if (session) auth.replaceSession(session);
    });
  return (
    <AuthPage
      title={t('auth.choosePassword.title')}
      sub={t('auth.choosePassword.sub')}
      onSubmit={submit}
      footer={
        <>
          <button className="btn left" type="button" onClick={() => void auth.signOut()}>
            {t('auth.account.signOut')}
          </button>
          <button className="btn primary" type="submit" disabled={shown} aria-busy={shown ? 'true' : undefined}>
            {shown ? <span className="spin"></span> : null}
            {t('auth.choosePassword.save')}
          </button>
        </>
      }
    >
      <PasswordFields state={change} prefix="cp" />
    </AuthPage>
  );
}
