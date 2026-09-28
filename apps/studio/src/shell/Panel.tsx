/**
 * The proposed-changes panel: nothing enters the model without approval here. Markup from
 * reference/ontaix-studio-reference.html lines 209-213; rows from `renderProps` (lines 587-592).
 */
import type { Proposal } from '../api/types';
import { NEUTRAL } from '../canvas/constants';
import { refStyle, useStore } from './dom';

const KIND: Record<Proposal['type'], string> = {
  concept: 'New concept',
  spec: 'Specialisation',
  relation: 'Relation',
  change: 'Change',
  source: 'Data source',
  bind: 'Binding',
  attr: 'Attribute',
};

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
        <button id="approveAll" disabled={!proposals.some((p) => p.ready)} onClick={() => void st.approveAll()}>
          Approve all
        </button>
        <button id="rejectAll" disabled={!proposals.length} onClick={() => void st.rejectAll()}>
          Reject all
        </button>
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
                <div className="what" dangerouslySetInnerHTML={{ __html: p.html }} />
                {p.why ? <div className="why">{p.why}</div> : null}
                <div className="act">
                  <button className="ok" disabled={!ok} onClick={() => void st.approve(p)}>
                    Approve
                  </button>
                  <button className="no" onClick={() => void st.reject(p)}>
                    Reject
                  </button>
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
