/**
 * How to read the lines, and the toggle above it. Built on the reference's legend card
 * (reference/ontaix-studio-reference.html lines 224-232) and its `toggleLegend` behaviour: each
 * row is an icon drawn in the canvas colours and a label of one or two words, with the full
 * explanation as the row's tooltip and as text for screen readers. The card, its toggle and the
 * keyboard hint stack in the right-hand dock (`.dock-r`), so no measuring is needed.
 */
import type { ReactNode } from 'react';

import { useStore } from './dom';

interface LegendEntry {
  key: string;
  label: string;
  detail: string;
  icon: ReactNode;
}

/** The rows in the reference's order; colours are the canvas colours of each kind of line. */
export const LEGEND: LegendEntry[] = [
  {
    key: 'rel',
    label: 'Relation',
    detail: 'A continuous line, brighter toward the target, with the action written on it',
    icon: (
      <>
        <path d="M2 11 Q14 3 30 7" stroke="#d9a15b" strokeWidth="1.8" fill="none" strokeLinecap="round" />
        <path d="M34 8 l-6.5 -3.4 v6.2 z" fill="#d9a15b" />
      </>
    ),
  },
  {
    key: 'isa',
    label: 'Is a',
    detail: 'A dashed line pointing to the parent it inherits from',
    icon: (
      <>
        <path d="M2 7 H24" stroke="#3fb8a9" strokeWidth="1.8" strokeDasharray="5 3.5" fill="none" />
        <path d="M34 7 l-9 -4.6 v9.2 z" className="hollow" stroke="#3fb8a9" strokeWidth="1.5" strokeLinejoin="round" />
      </>
    ),
  },
  {
    key: 'eq',
    label: 'Equivalent',
    detail: 'A dotted line with arrows at both ends, between concepts of different companies',
    icon: (
      <>
        <path d="M9 7 H27" className="ink" strokeWidth="1.8" strokeDasharray="1.5 3.5" strokeLinecap="round" fill="none" />
        <path d="M2 7 l7 -3.8 v7.6 z M34 7 l-7 -3.8 v7.6 z" className="inkfill" />
      </>
    ),
  },
  {
    key: 'conflict',
    label: 'Conflict',
    detail: 'A zigzag line: two definitions share one name',
    icon: <path d="M2 7 l4 -4 l5 8 l5 -8 l5 8 l5 -8 l5 8 l3 -4" stroke="#d95a68" strokeWidth="1.8" strokeLinejoin="round" fill="none" />,
  },
  {
    key: 'bind',
    label: 'Data binding',
    detail: 'A line from a data source (the square) that feeds the concept with records',
    icon: (
      <>
        <rect x="1.5" y="2.5" width="9" height="9" rx="2.2" fill="none" stroke="#d6bd8a" strokeWidth="1.6" />
        <path d="M11 7 H28" stroke="#d6bd8a" strokeWidth="1.5" fill="none" />
        <path d="M34 7 l-6 -3.2 v6.4 z" fill="#d6bd8a" />
      </>
    ),
  },
  {
    key: 'pending',
    label: 'Pending',
    detail: 'Drawn lighter until you approve it',
    icon: (
      <>
        <path d="M2 11 Q14 3 30 7" stroke="#d9a15b" strokeOpacity=".4" strokeWidth="1.8" fill="none" strokeLinecap="round" />
        <path d="M34 8 l-6.5 -3.4 v6.2 z" fill="#d9a15b" fillOpacity=".4" />
      </>
    ),
  },
];

export function Legend() {
  const st = useStore();
  const settings = st.ui.settings;
  const off = st.ui.legendOff;

  return (
    <>
      <button
        className="legend-toggle"
        id="legendToggle"
        aria-expanded={!off}
        aria-controls="legend"
        title="Show or hide the legend (L)"
        style={{ display: settings && !settings.legend ? 'none' : undefined }}
        onClick={() => st.toggleLegend()}
      >
        {off ? 'Show legend' : 'Hide legend'}
      </button>
      <aside className={`legend${off ? ' off' : ''}`} id="legend" aria-label="How to read the lines">
        <div className="title">Relationships</div>
        <ul>
          {LEGEND.map((e) => (
            <li className="row" key={e.key} data-k={e.key} title={e.detail}>
              <svg viewBox="0 0 36 14" aria-hidden="true">
                {e.icon}
              </svg>
              <b>{e.label}</b>
              <span className="sr">{`: ${e.detail}`}</span>
            </li>
          ))}
        </ul>
      </aside>
    </>
  );
}
