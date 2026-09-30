/**
 * `#adminAccount`, in the head of the admin portal and of the platform portal before the ×:
 * the signed-in email, `Change password`, `Sign out`, and `End support` while a super admin's
 * support session is open. Rendered only with a live session; a development identity header
 * has none, and the screenshot harness hides it in reference-parity captures.
 */
import { failed } from '../admin/adminData';
import { BusyButton } from '../shell/busy';
import { refStyle } from '../shell/dom';
import { auth, useAuth } from './authStore';
import { openChangePassword } from './ChangePasswordDialog';

/** `end` pushes the controls to the right of a head that has no theme button before them. */
export function AccountControls({ end }: { end?: boolean }) {
  const { session } = useAuth();
  if (!session) return null;
  return (
    <div id="adminAccount" ref={refStyle(`display:inline-flex;align-items:center;gap:8px;margin-left:${end ? 'auto' : '8px'}`)}>
      <span>{session.account.email}</span>
      <button className="btn" id="changePassword" onClick={() => openChangePassword()}>
        Change password
      </button>
      <BusyButton className="btn" id="signOut" onClick={() => auth.signOut()}>
        Sign out
      </BusyButton>
      {session.support ? (
        <BusyButton className="btn" id="endSupport" onClick={() => auth.endSupport().catch(failed)}>
          End support
        </BusyButton>
      ) : null}
    </div>
  );
}
