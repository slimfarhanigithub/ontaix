/**
 * The demo brain's controls: the small brain button at the end of the tool row, which starts the
 * demo and stops it; Escape stops it too. Nothing else shows while it grows, so the brain grows on
 * the canvas as a real model would; a screen reader hears when it has finished growing.
 */
import { useEffect, useState } from 'react';

import { formatNumber, useT } from '../i18n/i18n';
import { now } from '../runtime/clock';
import { useStore } from '../shell/dom';
import { brainGrown } from './brainDemo';

/** How often the status reads the growth, in milliseconds. */
const TICK_MS = 250;

/** The brain icon: two hemispheres with a fold in each. */
export function BrainIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d="M8 3.2C7.2 2.3 5.4 2.3 4.7 3.5 3.3 3.6 2.6 5 3.1 6.1 2.2 6.9 2.3 8.5 3.4 9.1c0 1.4 1.3 2.4 2.6 1.9.6 1 1.5 1.2 2 .6z" />
      <path d="M8 3.2c.8-.9 2.6-.9 3.3.3 1.4.1 2.1 1.5 1.6 2.6.9.8.8 2.4-.3 3 0 1.4-1.3 2.4-2.6 1.9-.6 1-1.5 1.2-2 .6z" />
      <path d="M8 3.2v8.4M5.3 6c.8 0 1.3.6 1.2 1.4M10.7 6c-.8 0-1.3.6-1.2 1.4M8 13.2v.8" />
    </svg>
  );
}

/** True while the demo brain is on and not fading out. */
export const brainRunning = (st: ReturnType<typeof useStore>): boolean => !!st.s.brain && st.s.brain.ending === null;

/** The tool row's brain button. */
export function BrainButton() {
  const st = useStore();
  const t = useT();
  const on = brainRunning(st);
  return (
    <button
      type="button"
      id="brainDemo"
      className="icon"
      title={on ? t('demo.button.stop') : t('demo.button.start')}
      aria-label={t('demo.button.label')}
      aria-pressed={on}
      onClick={() => (on ? st.stopBrain() : st.startBrain())}
    >
      <BrainIcon />
    </button>
  );
}

/** A polite live region, present while the demo brain is on, that says when it has grown. Nothing shows on screen. */
export function BrainStatus() {
  const st = useStore();
  const t = useT();
  const d = st.s.brain;
  const on = brainRunning(st);
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!on) return;
    const id = window.setInterval(() => setTick((k) => k + 1), TICK_MS);
    return () => window.clearInterval(id);
  }, [on]);
  if (!d || !on) return null;
  const grown = brainGrown(d, now());
  const concepts = grown ? d.cells.filter((c) => !c.story?.source).length : 0;
  return (
    <span className="sr" id="brainStatus" aria-live="polite">
      {grown ? t('demo.bar.grown', { n: formatNumber(concepts) }) : ''}
    </span>
  );
}
