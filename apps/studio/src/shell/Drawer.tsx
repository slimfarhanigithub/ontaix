/**
 * What the model knows about a cell, and its lineage. Markup from
 * reference/ontaix-studio-reference.html line 214; content from `openDrawer` (lines 637-646)
 * and `showLineage` (lines 653-662).
 */
import { useEffect, useRef } from 'react';

import { ancestorsOf, childrenOf, descendantsOf } from '../canvas/lineage';
import type { Node } from '../canvas/types';
import { useStore } from './dom';

const escapeHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export function Drawer() {
  const st = useStore();
  const s = st.s;
  const n = st.ui.drawerNode;
  const lineageOn = !!n && s.lineageNode === n;
  const line = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (n && lineageOn) {
      const anc = ancestorsOf(n),
        desc = descendantsOf(s, n);
      st.caption(
        `Lineage of ${n.label}`,
        `${anc.length ? anc.map((a) => a.label).join(' → ') + ' → ' : ''}${n.label}${desc.length ? ` → ${desc.length} descendant${desc.length === 1 ? '' : 's'}` : ''}. Everything else is dimmed.`,
      );
    }
    // The caption follows the lineage focus, not every store change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n, lineageOn]);

  if (!n) {
    return (
      <section className="drawer" id="drawer" aria-live="polite">
        <button className="x" id="drawerClose" aria-label="Close">
          ×
        </button>
        <h2>
          <i id="drDot"></i>
          <span id="drName"></span>
        </h2>
        <div className="meta" id="drMeta"></div>
        <div className="src" id="drSrc"></div>
        <h3 id="drAttrTitle">Attributes</h3>
        <div id="drAttrs"></div>
        <div className="actions">
          <button id="drGrow">Grow a concept from it</button>
          <button id="drLineage" aria-pressed="false">
            Lineage
          </button>
        </div>
        <div id="drLine" style={{ display: 'none' }}></div>
      </section>
    );
  }

  const d = n.domain;
  const bindCount = (pending: boolean) => s.links.filter((l) => l.kind === 'bind' && l.a === n && l.pending === pending).length;
  const meta =
    n.kind === 'root'
      ? `<b>${n.company?.name}</b><br>${n.sub || ''}<br>${n.company?.domains.filter((x) => s.nodes.some((m) => m.domain === x && !m.dying)).length} domain products · ${s.nodes.filter((m) => m.company === n.company && m.kind === 'concept').length} concepts`
      : n.kind === 'source'
        ? `<b>${n.sub}</b> · ${n.company?.name}<br>${bindCount(false)} concepts bound · ${bindCount(true)} pending`
        : `<b>${d ? d.name : '—'}</b> · domain product owned by ${d ? d.owner : '—'} · v${d ? d.version.toFixed(1) : '—'}<br>${n.pending ? 'awaiting approval' : 'approved'} · ${s.links.filter((l) => (l.a === n || l.b === n) && l.kind !== 'bind').length} relations`;
  let srcClass = 'src',
    srcHtml: string;
  if (n.kind === 'source')
    srcHtml = `<b>${n.label}</b> feeds: ${s.links.filter((l) => l.kind === 'bind' && l.a === n).map((l) => l.b.label).join(', ') || 'nothing yet'}`;
  else if (n.bound)
    srcHtml = `Bound to <b>${n.bound.source.label}</b> · ${n.bound.records.toLocaleString('en-GB')} records · fresh ${n.bound.fresh}`;
  else {
    srcClass = 'src none';
    srcHtml = n.kind === 'root' ? '<b>Company</b>' : `<b>No data behind it yet.</b> Bind it to a system to read its attributes.`;
  }

  const lineageHtml = lineageOn ? lineage(st, n) : '';

  return (
    <section className="drawer on" id="drawer" aria-live="polite">
      <button className="x" id="drawerClose" aria-label="Close" onClick={() => st.closeDrawer()}>
        ×
      </button>
      <h2>
        <i id="drDot" style={{ color: n.kind === 'source' ? s.BRASS : n.color }}></i>
        <span id="drName">{n.label + (n.sub && n.kind !== 'source' ? ' · ' + n.sub : '')}</span>
      </h2>
      <div className="meta" id="drMeta" dangerouslySetInnerHTML={{ __html: meta }} />
      <div className={srcClass} id="drSrc" dangerouslySetInnerHTML={{ __html: srcHtml }} />
      <h3 id="drAttrTitle" style={{ display: n.attrs && n.attrs.length ? undefined : 'none' }}>
        Attributes
      </h3>
      <div id="drAttrs">
        {(n.attrs || []).map((a) => (
          <div className="attr" key={a.sid || a.name}>
            <b>{a.name}</b>
            <span className={`state ${a.state === 'proposed' ? 'new' : ''}`}>
              {a.state === 'proposed' ? 'found in data · pending' : 'approved'}
            </span>
            <span className="col">{`${a.type} · ${a.col}`}</span>
            <div className="fill" title={`${a.fill} percent filled`}>
              <i style={{ width: `${a.fill}%` }}></i>
            </div>
          </div>
        ))}
      </div>
      <div className="actions">
        <button
          id="drGrow"
          style={{ display: n.kind === 'source' ? 'none' : undefined }}
          onClick={() => {
            const v = st.renderer?.v;
            st.openNewBox(n, (v ? v.W : innerWidth) * 0.35, (v ? v.H : innerHeight) * 0.4);
          }}
        >
          Grow a concept from it
        </button>
        <button
          id="drLineage"
          aria-pressed={lineageOn}
          style={{ display: n.kind === 'concept' ? undefined : 'none' }}
          onClick={() => st.toggleLineage()}
        >
          Lineage
        </button>
      </div>
      <div
        id="drLine"
        ref={line}
        style={{ display: lineageOn ? undefined : 'none' }}
        dangerouslySetInnerHTML={{ __html: lineageHtml }}
        onClick={(e) => {
          const b = (e.target as HTMLElement).closest('[data-go]') as HTMLElement | null;
          if (!b) return;
          const m = s.nodes.find((x) => String(x.id) === b.dataset.go);
          if (m) st.goTo(m);
        }}
      ></div>
    </section>
  );
}

/** Ancestry, descendants and data lineage of a cell, as HTML. */
function lineage(st: ReturnType<typeof useStore>, n: Node): string {
  const s = st.s;
  const anc = ancestorsOf(n),
    desc = descendantsOf(s, n);
  const when = (x: Node) => st.when(x);
  const how = (x: Node) => {
    const l = x.birthLink;
    if (!l || !x.parent) return '';
    return l.kind === 'isa'
      ? `is a ${x.parent.label}`
      : l.a === x
        ? `${x.label} ${l.label} ${x.parent.label}`
        : `${x.parent.label} ${l.label} ${x.label}`;
  };
  const chain = [...anc, n]
    .map(
      (x) =>
        `<div class="step${x === n ? ' me' : ''}" style="color:${x.kind === 'root' ? '#d8deee' : x.color}"><i></i><div><b data-go="${x.id}">${escapeHtml(x.label)}</b>${x.kind === 'root' ? '<small>the company</small>' : `<small>${escapeHtml(how(x))}${x.domain ? ' · ' + x.domain.name : ''}${x.bornAt ? ' · born ' + when(x) : ''}${x.pending ? ' · awaiting approval' : ''}</small>`}</div></div>`,
    )
    .join('');
  const kids = childrenOf(s, n);
  const kidsHtml = kids.length
    ? `<div class="kids">${kids.map((k) => `<b data-go="${k.id}">${escapeHtml(k.label)}</b> <em>· ${escapeHtml(how(k))}${descendantsOf(s, k).length ? ' · ' + descendantsOf(s, k).length + ' below' : ''}</em>`).join('<br>')}</div>`
    : '<div class="kids" style="color:var(--ink-3)">Nothing has been born from it yet.</div>';
  const data = n.bound
    ? `<div class="step" style="color:${s.BRASS}"><i></i><div><b data-go="${n.bound.source.id}">${escapeHtml(n.bound.source.label)}</b><small>feeds ${escapeHtml(n.label)} · ${n.bound.records.toLocaleString('en-GB')} records · fresh ${n.bound.fresh}</small></div></div><div class="step me" style="color:${n.color}"><i></i><div><b>${escapeHtml(n.label)}</b><small>${(n.attrs || []).filter((a) => a.state === 'approved').length} attributes read from ${escapeHtml(n.bound.source.label)}</small></div></div>`
    : `<div class="kids" style="color:var(--ink-3)">No data behind it yet.</div>`;
  return `<div class="lin"><h3>Ancestry · ${anc.length} generation${anc.length === 1 ? '' : 's'} from ${escapeHtml(anc[0] ? anc[0].label : n.label)}</h3>${chain}<h3>Descendants · ${desc.length}</h3>${kidsHtml}<h3>Data lineage</h3>${data}</div>`;
}
