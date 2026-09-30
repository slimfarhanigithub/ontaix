/**
 * The teach bar history: the last captions and refusals, newest at the bottom next to the input,
 * shown above the bar while it is open. Rows use the drawer's section title and attribute rhythm;
 * a new row enters with the panel's `propin` animation.
 */
import { useEffect, useRef } from 'react';

import { useStore } from './dom';

export function TeachLog({ expanded }: { expanded: boolean }) {
  const st = useStore();
  const history = st.ui.history;
  const ref = useRef<HTMLDivElement>(null);
  const newest = history[history.length - 1]?.seq ?? 0;
  useEffect(() => {
    const el = ref.current;
    if (el && expanded) el.scrollTop = el.scrollHeight;
  }, [expanded, newest]);
  return (
    <div className="hist" id="teachLog" role="log" aria-label="Recent captions" tabIndex={0} hidden={!expanded} ref={ref}>
      <h3>Recent</h3>
      {history.map((h) => (
        <div key={h.seq} className={h.refused ? 'refused' : undefined}>
          <b>{h.kicker}</b>
          <p>{h.text}</p>
        </div>
      ))}
    </div>
  );
}
