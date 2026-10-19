/**
 * The demo brain's controls: the small brain button at the end of the tool row, which starts the
 * demo and stops it, and the demo bar shown while it runs, with what has grown so far, a
 * progress bar, Pause or Resume (Replay once grown) and Stop. Escape stops it too. A screen
 * reader hears when the brain has finished growing.
 */
import { useEffect, useState } from 'react';

import { now } from '../runtime/clock';
import { useStore } from '../shell/dom';
import { bornCount, bornDomains, bornLinks, brainPhase, type BrainDemo } from './brainDemo';

/** How often the demo bar reads the growth, in milliseconds. */
const TICK_MS = 250;

const number = (n: number): string => n.toLocaleString('en-GB');

const COUNT_WORDS = ['no', 'one', 'two', 'three'];

/** The demo bar's title for what the demo shows at `t`. */
export function brainTitle(d: BrainDemo, t: number): string {
  if (d.pausedAt !== null) return 'Demo brain paused';
  switch (brainPhase(d, t)) {
    case 'company':
      return d.company ? `Starting from ${d.company}` : 'Starting a demo brain';
    case 'domains':
      return `Growing ${COUNT_WORDS[d.storyDomains] ?? d.storyDomains} domain${d.storyDomains === 1 ? '' : 's'}`;
    case 'brain':
      return 'Growing a demo brain';
    default:
      return 'Demo brain grown';
  }
}

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
  const on = brainRunning(st);
  return (
    <button
      type="button"
      id="brainDemo"
      className="icon"
      title={on ? 'Stop the demo brain (Esc)' : 'Grow a demo brain: a large example ontology drawn on the canvas, never saved'}
      aria-label="Grow a demo brain"
      aria-pressed={on}
      onClick={() => (on ? st.stopBrain() : st.startBrain())}
    >
      <BrainIcon />
    </button>
  );
}

/** The demo bar, shown while the demo brain is on. */
export function BrainBar() {
  const st = useStore();
  const d = st.s.brain;
  const on = brainRunning(st);
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!on) return;
    const id = window.setInterval(() => setTick((k) => k + 1), TICK_MS);
    return () => window.clearInterval(id);
  }, [on]);
  if (!d || !on) return null;
  const t = now();
  const born = bornCount(d, t);
  const total = d.cells.length;
  const grown = brainPhase(d, t) === 'grown';
  const paused = d.pausedAt !== null;
  const concepts = born;
  const domains = bornDomains(d, t);
  const pct = total ? Math.round((born / total) * 100) : 100;
  const title = brainTitle(d, t);
  return (
    <div className="brainbar" id="brainBar" role="region" aria-label="Demo brain">
      <span className="bb-icon">
        <BrainIcon />
      </span>
      <div className="bb-text">
        <b>{title}</b>
        <span>
          {number(concepts)} concepts · {number(bornLinks(d, t))} relations · {domains} domain product{domains === 1 ? '' : 's'} · not saved
        </span>
        <div className="bb-progress" role="progressbar" aria-label="Growth" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
          <i style={{ width: `${pct}%` }}></i>
        </div>
      </div>
      {grown ? (
        <button type="button" id="brainReplay" className="bb-btn" title="Grow it again" aria-label="Grow the demo brain again" onClick={() => st.replayBrain()}>
          <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
            <path d="M3 8a5 5 0 1 0 1.6-3.7M3 2.5v2.8h2.8" />
          </svg>
        </button>
      ) : (
        <button
          type="button"
          id="brainPause"
          className="bb-btn"
          title={paused ? 'Let it grow on' : 'Pause the growth'}
          aria-label={paused ? 'Resume the demo brain' : 'Pause the demo brain'}
          onClick={() => st.toggleBrainPause()}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
            {paused ? <path d="M5 3.5v9l7.5-4.5z" /> : <path d="M5.5 3.5v9M10.5 3.5v9" />}
          </svg>
        </button>
      )}
      <button type="button" id="brainStop" className="bb-btn" title="Stop the demo (Esc)" aria-label="Stop the demo brain" onClick={() => st.stopBrain()}>
        <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <path d="M4 4l8 8M12 4l-8 8" />
        </svg>
      </button>
      <span className="sr" aria-live="polite">
        {grown ? `The demo brain has grown: ${number(concepts)} concepts.` : ''}
      </span>
    </div>
  );
}
