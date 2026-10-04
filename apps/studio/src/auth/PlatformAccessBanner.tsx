/**
 * `#platformAccess`: the banner a super admin sees for the whole time he acts inside an
 * organization he entered from the platform portal, above everything else of the Studio and
 * the admin portal. It names the organization, counts down the minutes of the hour of access,
 * and carries `Exit`, which hands the session back to the platform portal. When the hour ends
 * the session is read again, which returns to the portal. Rendered only while the session's
 * `acting` is set.
 */
import { useEffect, useRef, useState } from 'react';

import { failed } from '../admin/adminData';
import { BusyButton } from '../shell/busy';
import { auth, useAuth } from './authStore';

/** How often the remaining minutes are recounted. */
const TICK_MS = 30_000;

export const actingText = (organization: string, minutesLeft: number): string => `Acting in ${organization} as platform super admin · ${minutesLeft} min left`;

/** Whole minutes until `until`, rounded up, never below zero. */
export function minutesLeft(until: string, now: number = Date.now()): number {
  return Math.max(0, Math.ceil((new Date(until).getTime() - now) / 60_000));
}

export function PlatformAccessBanner() {
  const { session } = useAuth();
  const acting = session?.acting ?? null;
  const until = acting?.until ?? null;
  const [now, setNow] = useState(() => Date.now());
  const refreshedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!until) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(timer);
  }, [until]);
  useEffect(() => {
    if (!until || new Date(until).getTime() > now || refreshedFor.current === until) return;
    refreshedFor.current = until;
    void auth.refresh();
  }, [until, now]);
  if (!acting || !until) return null;
  return (
    <div className="platform-access" id="platformAccess" role="status">
      <i></i>
      <span>{actingText(acting.organization.name, minutesLeft(until, now))}</span>
      <BusyButton className="btn" id="exitOrganization" onClick={() => auth.exitOrganization().catch(failed)}>
        Exit
      </BusyButton>
    </div>
  );
}
