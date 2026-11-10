/**
 * The teach bar's status slot: the reference's `.spin` ring and `Processing` while teach bar
 * parses are in flight (typed, spoken or imported), with `· <n> queued` when more wait behind
 * the first. It appears once the wait passes BUSY_DELAY_MS and, once shown, stays at least
 * STATUS_MIN_MS so it never flickers. Empty, the slot takes no space.
 */
import { useEffect, useRef, useState } from 'react';

import { useT } from '../i18n/i18n';
import { BUSY_DELAY_MS } from './busy';
import { useStore } from './dom';

/** The shortest time the status stays once shown, in milliseconds. */
export const STATUS_MIN_MS = 400;

/** True once `active` has stayed true for `delay`; once true, stays true at least `min` after it turned true. */
export function useShownAtLeast(active: boolean, delay: number = BUSY_DELAY_MS, min: number = STATUS_MIN_MS): boolean {
  const [shown, setShown] = useState(false);
  const since = useRef(0);
  useEffect(() => {
    if (active && !shown) {
      const t = setTimeout(() => {
        since.current = Date.now();
        setShown(true);
      }, delay);
      return () => clearTimeout(t);
    }
    if (!active && shown) {
      const t = setTimeout(() => setShown(false), Math.max(0, min - (Date.now() - since.current)));
      return () => clearTimeout(t);
    }
  }, [active, shown, delay, min]);
  return shown;
}

export function TeachStatus() {
  const st = useStore();
  const t = useT();
  const pending = st.ui.processing;
  const shown = useShownAtLeast(pending > 0);
  const label = pending > 1 ? t('teach.bar.processingQueued', { n: pending - 1 }) : t('teach.bar.processing');
  return (
    <span id="teachStatus" className="status2" role="status">
      {shown ? (
        <>
          <span className="spin"></span>
          <span className="lbl">{label}</span>
        </>
      ) : null}
    </span>
  );
}
