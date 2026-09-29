/**
 * The caption under the canvas: a kicker and a sentence typed one character every 16 ms
 * (4 ms with reduced motion). Ported from reference/ontaix-studio-reference.html line 733.
 */
import { useEffect, useRef } from 'react';

import { REDUCED } from '../canvas/constants';
import { useDelayed } from './busy';
import { useStore } from './dom';

export function Caption() {
  const st = useStore();
  const { kicker, text, seq } = st.ui.caption;
  const ref = useRef<HTMLParagraphElement>(null);
  const processing = useDelayed(st.ui.processing > 0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.textContent = '';
    let i = 0;
    const typer = setInterval(
      () => {
        i++;
        el.textContent = text.slice(0, i);
        if (i >= text.length) clearInterval(typer);
      },
      REDUCED ? 4 : 16,
    );
    return () => clearInterval(typer);
  }, [seq, text]);
  return (
    <div className="caption">
      <small id="captionKicker">
        {processing ? (
          <>
            <span className="spin"></span>Processing
          </>
        ) : (
          kicker
        )}
      </small>
      <p id="captionText" ref={ref}></p>
    </div>
  );
}
