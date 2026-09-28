/**
 * How to read the lines, and the toggle above it. Markup from
 * reference/ontaix-studio-reference.html lines 224-232; behaviour from `toggleLegend` /
 * `placeLegendToggle` (lines 549-551).
 */
import { useEffect, useRef } from 'react';

import { useStore } from './dom';

export function Legend() {
  const st = useStore();
  const settings = st.ui.settings;
  const off = st.ui.legendOff;
  const legend = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);

  const place = () => {
    const lg = legend.current,
      b = toggle.current;
    if (!lg || !b) return;
    const base = 64;
    const h = lg.classList.contains('off') ? 0 : lg.offsetHeight + 8;
    b.style.bottom = `calc(${base + h}px + env(safe-area-inset-bottom,0px))`;
  };

  useEffect(() => {
    const t = setTimeout(place, 50);
    addEventListener('resize', place);
    return () => {
      clearTimeout(t);
      removeEventListener('resize', place);
    };
  }, []);

  useEffect(() => {
    place();
  }, [off]);

  return (
    <>
      <button
        className="legend-toggle"
        id="legendToggle"
        ref={toggle}
        aria-expanded={!off}
        title="Show or hide the legend (L)"
        style={{ display: settings && !settings.legend ? 'none' : undefined }}
        onClick={() => st.toggleLegend()}
      >
        {off ? 'Show legend' : 'Hide legend'}
      </button>
      <aside className={`legend${off ? ' off' : ''}`} id="legend" aria-label="How to read the lines" ref={legend}>
        <div className="title">Relationships</div>
        <div className="row">
          <svg viewBox="0 0 52 14">
            <defs>
              <linearGradient id="lgA" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0" stopColor="#d9a15b" stopOpacity=".22" />
                <stop offset="1" stopColor="#d9a15b" stopOpacity=".9" />
              </linearGradient>
            </defs>
            <path d="M2 8 Q26 2 45 7" stroke="url(#lgA)" strokeWidth="1.3" fill="none" strokeLinecap="round" />
            <path d="M49 7 l-5.5 -2.6 v5.2 z" fill="#d9a15b" />
            <rect x="16" y="1.5" width="18" height="8" rx="4" fill="#070b16" stroke="#d9a15b" strokeOpacity=".45" strokeWidth=".8" />
            <text x="25" y="7.6" fontSize="5.2" fill="#eef2fb" textAnchor="middle" fontFamily="Sora, sans-serif">
              action
            </text>
          </svg>
          <div>
            <b>Relation</b> · continuous, brighter toward the target, the action on it
          </div>
        </div>
        <div className="row">
          <svg viewBox="0 0 52 14">
            <path d="M2 7 H40" stroke="#3fb8a9" strokeWidth="1.4" strokeDasharray="6 5" fill="none" />
            <path d="M50 7 l-9 -4.5 v9 z" fill="#070b16" stroke="#3fb8a9" strokeWidth="1.3" />
          </svg>
          <div>
            <b>Is a</b> · dashed, points to the parent it inherits from
          </div>
        </div>
        <div className="row">
          <svg viewBox="0 0 52 14">
            <path d="M8 7 H44" stroke="#e6ebf7" strokeWidth="1.1" strokeDasharray="2 5" fill="none" />
            <path d="M2 7 l7 -3.5 v7 z" fill="#e6ebf7" />
            <path d="M50 7 l-7 -3.5 v7 z" fill="#e6ebf7" />
          </svg>
          <div>
            <b>Equivalent to</b> · dotted, both ways, across companies
          </div>
        </div>
        <div className="row">
          <svg viewBox="0 0 52 14">
            <path d="M2 7 l6 -3 l6 5 l6 -4 l6 4 l6 -4 l6 3 l4 -1" stroke="#d95a68" strokeWidth="1.3" fill="none" />
          </svg>
          <div>
            <b>Conflicts with</b> · two definitions, one name
          </div>
        </div>
        <div className="row">
          <svg viewBox="0 0 52 14">
            <rect x="1" y="2" width="10" height="10" rx="2.5" fill="none" stroke="#d6bd8a" strokeWidth="1.2" />
            <path d="M12 7 H44" stroke="#d6bd8a" strokeWidth="1" fill="none" />
            <path d="M49 7 l-5 -2.4 v4.8 z" fill="#d6bd8a" />
          </svg>
          <div>
            <b>Bound to</b> · a system feeds the concept with data
          </div>
        </div>
        <div className="row">
          <svg viewBox="0 0 52 14">
            <path d="M2 8 Q26 2 45 7" stroke="#d9a15b" strokeOpacity=".4" strokeWidth="1.3" fill="none" strokeLinecap="round" />
            <path d="M49 7 l-5.5 -2.6 v5.2 z" fill="#d9a15b" fillOpacity=".4" />
          </svg>
          <div>
            <b>Awaiting approval</b> · lighter until you approve it
          </div>
        </div>
      </aside>
    </>
  );
}
