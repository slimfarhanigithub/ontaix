/**
 * The admin portal's `Change password` dialog: the reference's `dialog()` frame with the three
 * password fields and `Save password`. A refusal keeps the dialog open with its message; success
 * closes it with the toast `Password changed`.
 */
import { store } from '../store/store';
import { DialogFrame } from '../shell/Dialog';
import { useBusyAction } from '../shell/busy';
import { auth } from './authStore';
import { PasswordFields, usePasswordChange } from './PasswordFields';

export function openChangePassword(): void {
  store.openDialog({ render: (close) => <ChangePasswordDialog close={close} /> });
}

function ChangePasswordDialog({ close }: { close: () => void }) {
  const change = usePasswordChange();
  const { shown, run } = useBusyAction();
  const save = () =>
    void run(async () => {
      const session = await change.save();
      if (!session) return;
      auth.replaceSession(session);
      close();
      store.toast2('Password changed', '');
    });
  return (
    <DialogFrame
      title="Change password"
      onClose={close}
      footer={
        <button className="btn primary" data-i="0" disabled={shown} aria-busy={shown ? 'true' : undefined} onClick={save}>
          {shown ? <span className="spin"></span> : null}
          Save password
        </button>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <PasswordFields state={change} prefix="chp" />
      </form>
    </DialogFrame>
  );
}
