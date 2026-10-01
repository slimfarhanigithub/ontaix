/**
 * The "Choose a new password" page, shown while `mustChangePassword` is true and nothing else
 * is reachable: the same card as the sign-in page, the three password fields, `Save password`
 * and a `Sign out` link-button on the left of the footer.
 */
import { useBusyAction } from '../shell/busy';
import { auth } from './authStore';
import { AuthPage } from './AuthPage';
import { PasswordFields, usePasswordChange } from './PasswordFields';

export function ChoosePassword() {
  const change = usePasswordChange();
  const { shown, run } = useBusyAction();
  const submit = () =>
    void run(async () => {
      const session = await change.save();
      if (session) auth.replaceSession(session);
    });
  return (
    <AuthPage
      title="Choose a new password"
      sub="Your password was set by an administrator. Choose your own to continue."
      onSubmit={submit}
      footer={
        <>
          <button className="btn left" type="button" onClick={() => void auth.signOut()}>
            Sign out
          </button>
          <button className="btn primary" type="submit" disabled={shown} aria-busy={shown ? 'true' : undefined}>
            {shown ? <span className="spin"></span> : null}
            Save password
          </button>
        </>
      }
    >
      <PasswordFields state={change} prefix="cp" />
    </AuthPage>
  );
}
