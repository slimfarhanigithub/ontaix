/**
 * The proposed-changes panel: nothing enters the model without approval here. Markup from
 * reference/ontaix-studio-reference.html lines 209-213; rows from `renderProps` (lines 587-592).
 * `Approve branch`, on a ready concept or specialisation with open proposals below it, is an
 * owner addition absent from the reference, in the row's existing button style. `Reject all`, and
 * `Reject` on a proposal with open proposals below it, ask first in the reference's own
 * `confirmDialog`, as neither can be undone. `Edit`, on a pending concept, specialisation or
 * relation, is an owner addition that edits the draft in place at its revision. Under 900 px the
 * panel is a full-screen sheet: opening it moves the focus to its ×, closing it gives the focus back
 * to `Show changes`.
 */
import { useEffect, useRef, useState } from 'react';

import { confirmDialog } from '../admin/actions';
import type { Proposal } from '../api/types';
import { NEUTRAL } from '../canvas/constants';
import { BusyButton } from './busy';
import { themedColour } from '../design/tokens';
import { t, useT, type MessageKey } from '../i18n/i18n';
import { refStyle, useStore } from './dom';
import { editableFields, PendingEdit } from './PendingEdit';
import { sanitizeHtml } from './sanitize';

/** The heading of a proposal whose server heading is absent, by type; a type without one reads as a change. */
const KIND: Partial<Record<Proposal['type'], MessageKey>> = {
  concept: 'shell.panel.kind.concept',
  spec: 'shell.panel.kind.spec',
  relation: 'shell.panel.kind.relation',
  change: 'shell.panel.kind.change',
  attr: 'shell.panel.kind.attr',
};

/** The heading of a proposal: the server's, else the one its type gives; a type without one reads as a change. */
const headingOf = (p: Proposal): string => p.heading || t(KIND[p.type] || 'shell.panel.kind.change');

/** Asks before rejecting every pending proposal. */
export function confirmRejectAll(count: number, rejectAll: () => Promise<void>): void {
  confirmDialog(t('shell.panel.rejectAllTitle', { n: count }), t('shell.panel.rejectAllBody'), t('shell.panel.rejectAll'), rejectAll, true);
}

/** Rejects a proposal, asking first when the open proposals below it go with it. */
export function rejectWithBranch(p: Proposal, reject: (p: Proposal) => Promise<void>): Promise<void> | void {
  const below = p.openBelow ?? 0;
  if (below <= 0) return reject(p);
  confirmDialog(t('shell.panel.rejectBranchTitle', { title: p.title, n: below }), t('shell.panel.rejectBranchBody'), t('shell.panel.reject'), () => reject(p), true);
}

/** The proposals `Approve branch` decides, the proposal itself included; 0 when the button is not offered. */
export function branchSize(p: Proposal): number {
  const below = p.openBelow ?? 0;
  return p.ready && (p.type === 'concept' || p.type === 'spec') && below > 0 ? below + 1 : 0;
}

export function Panel() {
  const st = useStore();
  const t = useT();
  const proposals = st.ui.proposals;
  /** The proposal whose draft is being edited in place. */
  const [editing, setEditing] = useState<string | null>(null);
  const sheet = st.ui.panelSheet;
  const opened = useRef(false);
  useEffect(() => {
    if (sheet) document.getElementById('panelHide')?.focus();
    else if (opened.current) document.getElementById('panelShow')?.focus();
    opened.current = sheet;
  }, [sheet]);
  // Crossing 900 px (a rotated tablet, a resized window) closes the sheet, so the side panel and
  // the sheet never mix and the sheet never comes back unasked.
  useEffect(() => {
    if (typeof matchMedia !== 'function') return;
    const narrow = matchMedia('(max-width:900px)');
    const close = () => st.closePanelSheet();
    narrow.addEventListener?.('change', close);
    return () => narrow.removeEventListener?.('change', close);
  }, [st]);
  return (
    <aside className="panel" aria-label={t('shell.panel.label')}>
      <h2>
        {t('shell.panel.label')} <span id="propCount">{proposals.length}</span>
        <button
          className="x"
          id="panelHide"
          aria-label={t('shell.panel.hide')}
          title={t('shell.panel.hideTitle')}
          ref={refStyle('margin-left:auto;all:unset;cursor:pointer;color:var(--ink-3);font-size:17px;padding:0 6px')}
          onClick={() => st.togglePanel()}
        >
          ×
        </button>
      </h2>
      <div className="bulk">
        <BusyButton id="approveAll" disabled={!proposals.some((p) => p.ready)} onClick={() => st.approveAll()}>
          {t('shell.panel.approveAll')}
        </BusyButton>
        <BusyButton id="rejectAll" disabled={!proposals.length} onClick={() => confirmRejectAll(proposals.length, () => st.rejectAll())}>
          {t('shell.panel.rejectAll')}
        </BusyButton>
      </div>
      <div className="list" id="propList">
        {!proposals.length ? (
          <div className="empty">{t('shell.panel.empty')}</div>
        ) : (
          proposals.map((p) => {
            const ok = p.ready;
            const color = themedColour(p.color || NEUTRAL);
            if (editing === p.id && editableFields(p))
              return (
                <div key={p.id} className={'prop' + (ok ? '' : ' blocked')}>
                  <div className="top">
                    <i
                      className={p.type === 'spec' ? 'spec' : p.type === 'relation' ? 'rel' : ''}
                      style={{ color, background: p.type === 'spec' ? 'transparent' : color }}
                    ></i>
                    {headingOf(p)}
                  </div>
                  <PendingEdit p={p} onDone={() => setEditing(null)} />
                </div>
              );
            return (
              <div key={p.id} className={'prop' + (ok ? '' : ' blocked')}>
                <div className="top">
                  <i
                    className={p.type === 'spec' ? 'spec' : p.type === 'relation' ? 'rel' : ''}
                    style={{ color, background: p.type === 'spec' ? 'transparent' : color }}
                  ></i>
                  {headingOf(p)}
                </div>
                <div className="what" dangerouslySetInnerHTML={{ __html: sanitizeHtml(p.html) }} />
                {p.why ? <div className="why">{p.why}</div> : null}
                <div className="act">
                  <BusyButton className="ok" disabled={!ok} onClick={() => st.approve(p)}>
                    {t('shell.panel.approve')}
                  </BusyButton>
                  <BusyButton className="no" onClick={() => rejectWithBranch(p, (q) => st.reject(q))}>
                    {t('shell.panel.reject')}
                  </BusyButton>
                  {branchSize(p) ? (
                    <BusyButton className="branch" onClick={() => st.approveBranch(p)}>
                      {t('shell.panel.approveBranch', { n: branchSize(p) })}
                    </BusyButton>
                  ) : null}
                  {editableFields(p) ? (
                    <button className="edit" data-ox-new="" title={t('shell.panel.editTitle')} onClick={() => setEditing(p.id)}>
                      {t('common.edit')}
                    </button>
                  ) : null}
                  {ok ? null : <span className="wait">{t('shell.panel.after', { what: p.waitFor || t('shell.panel.previousItem') })}</span>}
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
