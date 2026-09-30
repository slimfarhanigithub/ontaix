/**
 * The caption, as the teach bar's disclosure button: a chevron, then the latest caption's kicker
 * and its sentence on one line, cut with an ellipsis. The sentence is typed one character every
 * 16 ms (4 ms with reduced motion), the typer of reference/ontaix-studio-reference.html line 733.
 * While the microphone listens the kicker reads `Listening` after the conflict dot and the text
 * holds the last finished words. Open, the button shows only the chevron and `Hide`, as the
 * history above holds the captions.
 */
import { useEffect, useRef, useState, type RefObject } from 'react';

import { REDUCED } from '../canvas/constants';
import { useStore } from './dom';

/** How long the chevron keeps the accent after a caption arrives cut short. */
const HINT_MS = 2000;

interface CaptionProps {
  expanded: boolean;
  onToggle: () => void;
  /** The last sentence the recogniser finished during the current recording. */
  heard: string;
  buttonRef: RefObject<HTMLButtonElement | null>;
}

export function Caption({ expanded, onToggle, heard, buttonRef }: CaptionProps) {
  const st = useStore();
  const latest = st.ui.history[st.ui.history.length - 1];
  const listening = st.ui.listening;
  const kicker = listening ? 'Listening' : latest?.kicker ?? '';
  const text = listening ? heard : latest?.text ?? '';
  const seq = listening ? -1 : latest?.seq ?? 0;
  const ref = useRef<HTMLSpanElement>(null);
  const [hint, setHint] = useState(false);
  const expandedRef = useRef(expanded);
  expandedRef.current = expanded;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.textContent = '';
    let i = 0;
    let hintTimer: ReturnType<typeof setTimeout> | undefined;
    const typer = setInterval(
      () => {
        i++;
        el.textContent = text.slice(0, i);
        if (i < text.length) return;
        clearInterval(typer);
        if (seq > 0 && !expandedRef.current && el.scrollWidth > el.clientWidth) {
          setHint(true);
          hintTimer = setTimeout(() => setHint(false), HINT_MS);
        }
      },
      REDUCED ? 4 : 16,
    );
    return () => {
      clearInterval(typer);
      clearTimeout(hintTimer);
      setHint(false);
    };
  }, [seq, text]);

  const refused = !listening && !!latest?.refused;
  return (
    <button
      type="button"
      className={`more${refused ? ' refused' : ''}${hint ? ' fresh' : ''}`}
      id="teachMore"
      ref={buttonRef}
      aria-expanded={expanded}
      aria-controls="teachLog"
      title={expanded ? 'Hide recent captions' : [kicker, text].filter(Boolean).join(' ')}
      onClick={onToggle}
    >
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <path d="M4 10l4-4 4 4" />
      </svg>
      <small id="captionKicker">
        {listening ? <i className="dot"></i> : null}
        {kicker}
      </small>
      <span id="captionText" className="txt" ref={ref}></span>
      <span className="hide">Hide</span>
    </button>
  );
}
