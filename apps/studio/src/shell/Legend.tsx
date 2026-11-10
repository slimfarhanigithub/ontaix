/**
 * How to read the lines, and the toggle above it. Built on the reference's legend card
 * (reference/ontaix-studio-reference.html lines 224-232) and its `toggleLegend` behaviour: each
 * row is an icon drawn in the canvas colours and a label of one or two words, with the full
 * explanation as the row's tooltip and as text for screen readers. The card, its toggle and the
 * keyboard hint stack in the right-hand dock (`.dock-r`), so no measuring is needed.
 */
import type { ReactNode } from 'react';

import { useT, type MessageKey } from '../i18n/i18n';
import { useStore } from './dom';

interface LegendEntry {
  key: string;
  /** The dictionary keys of the one-word label and of the full explanation. */
  label: MessageKey;
  detail: MessageKey;
  icon: ReactNode;
}

/** The rows in the reference's order; each icon takes the token its kind of line is drawn with. */
export const LEGEND: LegendEntry[] = [
  {
    key: 'rel',
    label: 'shell.legend.relation',
    detail: 'shell.legend.relationDetail',
    icon: (
      <>
        <path d="M2 11 Q14 3 30 7" stroke="var(--text-2)" strokeWidth="1.8" fill="none" strokeLinecap="round" />
        <path d="M34 8 l-6.5 -3.4 v6.2 z" fill="var(--text-2)" />
      </>
    ),
  },
  {
    key: 'isa',
    label: 'shell.legend.isa',
    detail: 'shell.legend.isaDetail',
    icon: (
      <>
        <path d="M2 7 H24" stroke="var(--link)" strokeWidth="1.8" strokeDasharray="5 3.5" fill="none" />
        <path d="M34 7 l-9 -4.6 v9.2 z" className="hollow" stroke="var(--link)" strokeWidth="1.5" strokeLinejoin="round" />
      </>
    ),
  },
  {
    key: 'eq',
    label: 'shell.legend.equivalent',
    detail: 'shell.legend.equivalentDetail',
    icon: (
      <>
        <path d="M9 7 H27" className="ink" strokeWidth="1.8" strokeDasharray="1.5 3.5" strokeLinecap="round" fill="none" />
        <path d="M2 7 l7 -3.8 v7.6 z M34 7 l-7 -3.8 v7.6 z" className="inkfill" />
      </>
    ),
  },
  {
    key: 'conflict',
    label: 'shell.legend.conflict',
    detail: 'shell.legend.conflictDetail',
    icon: <path d="M2 7 l4 -4 l5 8 l5 -8 l5 8 l5 -8 l5 8 l3 -4" stroke="var(--danger)" strokeWidth="1.8" strokeLinejoin="round" fill="none" />,
  },
  {
    key: 'pending',
    label: 'shell.legend.pending',
    detail: 'shell.legend.pendingDetail',
    icon: (
      <>
        <path d="M2 11 Q14 3 30 7" stroke="var(--text-2)" strokeOpacity=".4" strokeWidth="1.8" fill="none" strokeLinecap="round" />
        <path d="M34 8 l-6.5 -3.4 v6.2 z" fill="var(--text-2)" fillOpacity=".4" />
      </>
    ),
  },
];

export function Legend() {
  const st = useStore();
  const t = useT();
  const settings = st.ui.settings;
  const off = st.ui.legendOff;

  return (
    <>
      <button
        className="legend-toggle"
        id="legendToggle"
        aria-expanded={!off}
        aria-controls="legend"
        title={t('shell.legend.toggleTitle')}
        style={{ display: settings && !settings.legend ? 'none' : undefined }}
        onClick={() => st.toggleLegend()}
      >
        {off ? t('shell.legend.show') : t('shell.legend.hide')}
      </button>
      <aside className={`legend${off ? ' off' : ''}`} id="legend" aria-label={t('shell.legend.label')}>
        <div className="title">{t('shell.legend.title')}</div>
        <ul>
          {LEGEND.map((e) => (
            <li className="row" key={e.key} data-k={e.key} title={t(e.detail)}>
              <svg viewBox="0 0 36 14" aria-hidden="true">
                {e.icon}
              </svg>
              <b>{t(e.label)}</b>
              <span className="sr">{`: ${t(e.detail)}`}</span>
            </li>
          ))}
        </ul>
      </aside>
    </>
  );
}
