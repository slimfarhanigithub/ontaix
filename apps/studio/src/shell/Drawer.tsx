/**
 * What the model knows about a cell, and its lineage. Markup from
 * reference/ontaix-studio-reference.html line 214; content from `openDrawer` (lines 637-646)
 * and `showLineage` (lines 653-662), without the data-source box and the data lineage, since no
 * cell has data behind it. Labels, subs and names are rendered as text. The action row holds one
 * button, More actions, whose menu offers every action on the cell: the reference's Grow a
 * concept from it and Lineage, and the owner's Expand, Rename, Move to domain and Delete, each a
 * dialog whose outcome is a proposal.
 */
import { useEffect } from 'react';

import { C, NEUTRAL } from '../canvas/constants';
import { ancestorsOf, childrenOf, descendantsOf } from '../canvas/lineage';
import type { Node } from '../canvas/types';
import { useDelayed } from './busy';
import { useStore } from './dom';
import { themedColour } from '../design/tokens';
import { useT } from '../i18n/i18n';
import { DrawerMoreMenu } from './DrawerMoreMenu';

const HEX = /^#[0-9a-f]{6}$/i;
const safeColour = (c: string, fallback: string) => (HEX.test(c) ? c : fallback);

export function Drawer() {
  const st = useStore();
  const t = useT();
  const s = st.s;
  const n = st.ui.drawerNode;
  const lineageOn = !!n && s.lineageNode === n;
  const expanding = useDelayed(!!n && st.ui.expanding === n);

  useEffect(() => {
    if (n && lineageOn) {
      const anc = ancestorsOf(n),
        desc = descendantsOf(s, n);
      st.caption(
        t('shell.drawer.lineageKicker', { label: n.label }),
        t('shell.drawer.lineageText', {
          chain: `${anc.length ? anc.map((a) => a.label).join(' → ') + ' → ' : ''}${n.label}`,
          descendants: desc.length ? t('shell.drawer.lineageDescendants', { n: desc.length }) : '',
        }),
      );
    }
    // The caption follows the lineage focus, not every store change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n, lineageOn]);

  if (!n) {
    return (
      <section className="drawer" id="drawer" aria-live="polite">
        <button className="x" id="drawerClose" aria-label={t('common.close')}>
          ×
        </button>
        <h2>
          <i id="drDot"></i>
          <span id="drName"></span>
        </h2>
        <div className="meta" id="drMeta"></div>
        <h3 id="drAttrTitle">{t('shell.drawer.attributes')}</h3>
        <div id="drAttrs"></div>
        <div className="actions"></div>
        <div id="drLine" style={{ display: 'none' }}></div>
      </section>
    );
  }

  const d = n.domain;
  const meta =
    n.kind === 'root' ? (
      <>
        <b>{n.company?.name}</b>
        <br />
        {n.sub || ''}
        <br />
        {t('shell.drawer.rootMeta', {
          domains: n.company?.domains.filter((x) => s.nodes.some((m) => m.domain === x && !m.dying)).length ?? 0,
          concepts: s.nodes.filter((m) => m.company === n.company && m.kind === 'concept').length,
        })}
      </>
    ) : (
      <>
        <b>{d ? d.name : '—'}</b>
        {t('shell.drawer.ownedBy', { owner: d ? d.owner : '—', version: d ? d.version.toFixed(1) : '—' })}
        <br />
        {t('shell.drawer.stateRelations', {
          state: n.pending ? t('shell.drawer.awaitingApproval') : t('shell.drawer.approved'),
          n: s.links.filter((l) => (l.a === n || l.b === n) && l.kind !== 'bind').length,
        })}
      </>
    );

  return (
    <section className="drawer on" id="drawer" aria-live="polite">
      <button className="x" id="drawerClose" aria-label={t('common.close')} onClick={() => st.closeDrawer()}>
        ×
      </button>
      <h2>
        <i id="drDot" style={{ color: themedColour(safeColour(n.color, NEUTRAL)) }}></i>
        <span id="drName">{n.label + (n.sub ? ' · ' + n.sub : '')}</span>
      </h2>
      <div className="meta" id="drMeta">
        {meta}
      </div>
      <h3 id="drAttrTitle" style={{ display: n.attrs && n.attrs.length ? undefined : 'none' }}>
        {t('shell.drawer.attributes')}
      </h3>
      <div id="drAttrs">
        {(n.attrs || []).map((a) => (
          <div className="attr" key={a.sid || a.name}>
            <b>{a.name}</b>
            <span className={`state ${a.state === 'proposed' ? 'new' : ''}`}>
              {a.state === 'proposed' ? t('shell.drawer.foundInData') : t('shell.drawer.approved')}
            </span>
            {/* A taught attribute shows its value where a source attribute shows its column, and has no fill bar. */}
            <span className="col">{`${a.type} · ${a.value ?? a.col}`}</span>
            {a.value === undefined ? (
              <div className="fill" title={t('shell.drawer.filled', { fill: a.fill })}>
                <i style={{ width: `${Math.max(0, Math.min(100, Number(a.fill) || 0))}%` }}></i>
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <div className="actions">
        {/* Keyed by the cell, so another selection starts with the menu closed. */}
        <DrawerMoreMenu key={n.id} node={n} expanding={expanding} />
      </div>
      <div id="drLine" style={{ display: lineageOn ? undefined : 'none' }}>
        {lineageOn ? <Lineage n={n} /> : null}
      </div>
    </section>
  );
}

/** Ancestry and descendants of a cell. */
function Lineage({ n }: { n: Node }) {
  const st = useStore();
  const t = useT();
  const s = st.s;
  const anc = ancestorsOf(n),
    desc = descendantsOf(s, n);
  const how = (x: Node) => {
    const l = x.birthLink;
    if (!l || !x.parent) return '';
    return l.kind === 'isa'
      ? t('shell.drawer.isA', { label: x.parent.label })
      : l.a === x
        ? `${x.label} ${l.label} ${x.parent.label}`
        : `${x.parent.label} ${l.label} ${x.label}`;
  };
  const kids = childrenOf(s, n);
  return (
    <div className="lin">
      <h3>{t('shell.drawer.ancestry', { n: anc.length, label: anc[0] ? anc[0].label : n.label })}</h3>
      {[...anc, n].map((x) => (
        <div key={x.id} className={`step${x === n ? ' me' : ''}`} style={{ color: themedColour(safeColour(x.kind === 'root' ? C.root : x.color, NEUTRAL)) }}>
          <i></i>
          <div>
            <b onClick={() => st.goTo(x)}>{x.label}</b>
            {x.kind === 'root' ? (
              <small>{t('shell.drawer.theCompany')}</small>
            ) : (
              <small>
                {`${how(x)}${x.domain ? t('shell.drawer.inDomain', { name: x.domain.name }) : ''}${x.bornAt ? t('shell.drawer.born', { when: st.when(x) }) : ''}${x.pending ? t('shell.drawer.pendingSuffix') : ''}`}
              </small>
            )}
          </div>
        </div>
      ))}
      <h3>{t('shell.drawer.descendants', { n: desc.length })}</h3>
      {kids.length ? (
        <div className="kids">
          {kids.map((k, i) => (
            <span key={k.id}>
              {i ? <br /> : null}
              <b onClick={() => st.goTo(k)}>{k.label}</b>{' '}
              <em>{`· ${how(k)}${descendantsOf(s, k).length ? t('shell.drawer.below', { n: descendantsOf(s, k).length }) : ''}`}</em>
            </span>
          ))}
        </div>
      ) : (
        <div className="kids" style={{ color: 'var(--ink-3)' }}>
          {t('shell.drawer.nothingBorn')}
        </div>
      )}
    </div>
  );
}
