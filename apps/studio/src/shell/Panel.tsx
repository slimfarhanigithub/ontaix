/**
 * The proposed-changes panel: nothing enters the model without approval here. Markup from
 * reference/ontaix-studio-reference.html lines 209-213; rows from `renderProps` (lines 587-592).
 * `Approve branch`, on a ready concept or specialisation with open proposals below it, is an
 * owner addition absent from the reference, in the row's existing button style. `Reject all`, and
 * `Reject` on a proposal with open proposals below it, ask first in the reference's own
 * `confirmDialog`, as neither can be undone.
 */
import { confirmDialog } from '../admin/actions';
import type { Proposal } from '../api/types';
import { NEUTRAL } from '../canvas/constants';
import { BusyButton } from './busy';
import { refStyle, useStore } from './dom';
import { sanitizeHtml } from './sanitize';

const KIND: Record<Proposal['type'], string> = {
  concept: 'New concept',
  spec: 'Specialisation',
  relation: 'Relation',
  change: 'Change',
  source: 'Data source',
  bind: 'Binding',
  attr: 'Attribute',
};

/** `n proposal` or `n proposals`. */
const countOf = (n: number) => `${n} proposal${n === 1 ? '' : 's'}`;

/** Asks before rejecting every pending proposal. */
export function confirmRejectAll(count: number, rejectAll: () => Promise<void>): void {
  confirmDialog(`Reject ${countOf(count)}?`, 'Every pending proposal is discarded. This cannot be undone.', 'Reject all', rejectAll, true);
}

/** Rejects a proposal, asking first when the open proposals below it go with it. */
export function rejectWithBranch(p: Proposal, reject: (p: Proposal) => Promise<void>): Promise<void> | void {
  const below = p.openBelow ?? 0;
  if (below <= 0) return reject(p);
  const rest = below === 1 ? 'the proposal below it' : `the ${below} proposals below it`;
  confirmDialog(
    `Reject ${p.title} and ${rest}?`,
    'Every proposal that grows from it is rejected with it. This cannot be undone.',
    'Reject',
    () => reject(p),
    true,
  );
}

/** The proposals `Approve branch` decides, the proposal itself included; 0 when the button is not offered. */
export function branchSize(p: Proposal): number {
  const below = p.openBelow ?? 0;
  return p.ready && (p.type === 'concept' || p.type === 'spec') && below > 0 ? below + 1 : 0;
}

export function Panel() {
  const st = useStore();
  const proposals = st.ui.proposals;
  return (
    <aside className="panel" aria-label="Proposed changes">
      <h2>
        Proposed changes <span id="propCount">{proposals.length}</span>
        <button
          className="x"
          id="panelHide"
          aria-label="Hide changes"
          title="Hide the changes panel (P)"
          ref={refStyle('margin-left:auto;all:unset;cursor:pointer;color:var(--ink-3);font-size:17px;padding:0 6px')}
          onClick={() => st.togglePanel()}
        >
          ×
        </button>
      </h2>
      <div className="bulk">
        <BusyButton id="approveAll" disabled={!proposals.some((p) => p.ready)} onClick={() => st.approveAll()}>
          Approve all
        </BusyButton>
        <BusyButton id="rejectAll" disabled={!proposals.length} onClick={() => confirmRejectAll(proposals.length, () => st.rejectAll())}>
          Reject all
        </BusyButton>
      </div>
      <div className="list" id="propList">
        {!proposals.length ? (
          <div className="empty">
            Nothing waiting. New cells divide off the model as soon as they are proposed, then stay only if you approve them here.
          </div>
        ) : (
          proposals.map((p) => {
            const ok = p.ready;
            const color = p.color || NEUTRAL;
            return (
              <div key={p.id} className={'prop' + (ok ? '' : ' blocked')}>
                <div className="top">
                  <i
                    className={p.type === 'spec' ? 'spec' : p.type === 'relation' || p.type === 'bind' ? 'rel' : ''}
                    style={{ color, background: p.type === 'spec' ? 'transparent' : color }}
                  ></i>
                  {p.heading || KIND[p.type]}
                </div>
                <div className="what" dangerouslySetInnerHTML={{ __html: sanitizeHtml(p.html) }} />
                {p.why ? <div className="why">{p.why}</div> : null}
                <div className="act">
                  <BusyButton className="ok" disabled={!ok} onClick={() => st.approve(p)}>
                    Approve
                  </BusyButton>
                  <BusyButton className="no" onClick={() => rejectWithBranch(p, (q) => st.reject(q))}>
                    Reject
                  </BusyButton>
                  {branchSize(p) ? (
                    <BusyButton className="branch" onClick={() => st.approveBranch(p)}>
                      {`Approve branch (${branchSize(p)})`}
                    </BusyButton>
                  ) : null}
                  {ok ? null : <span className="wait">{`after ${p.waitFor || 'a previous item'}`}</span>}
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
