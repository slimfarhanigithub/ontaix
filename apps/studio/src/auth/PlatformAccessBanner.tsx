/**
 * `#platformAccess`: the banner a super admin sees for the whole time he acts inside an
 * organization he entered from the platform portal, above everything else of the Studio and
 * the admin portal. It names the organization and carries `Exit`, which hands the session back
 * to the platform portal. Rendered only while the session's `acting` is set.
 */
import { failed } from '../admin/adminData';
import { BusyButton } from '../shell/busy';
import { auth, useAuth } from './authStore';

export const actingText = (organization: string): string => `Acting in ${organization} as platform super admin`;

export function PlatformAccessBanner() {
  const { session } = useAuth();
  const acting = session?.acting ?? null;
  if (!acting) return null;
  return (
    <div className="platform-access" id="platformAccess" role="status">
      <i></i>
      <span>{actingText(acting.organization.name)}</span>
      <BusyButton className="btn" id="exitOrganization" onClick={() => auth.exitOrganization().catch(failed)}>
        Exit
      </BusyButton>
    </div>
  );
}
