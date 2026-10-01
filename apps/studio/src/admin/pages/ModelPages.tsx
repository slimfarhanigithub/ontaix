/**
 * The Model group of the admin portal: Entities, Relationships, Bindings, Companies and Domain
 * products (`pageEntities` to `pageDomains`, reference lines 991-1014). Rows come from the scene
 * the canvas shows; every change they offer is a proposal. The owner additions for editing, each
 * marked `data-ox-new` and hidden from the screenshot suite: a checkbox column and `Delete
 * selected` on Entities and Domain products, `Move` per entity, `New domain`, `Edit` and `Delete`
 * per domain product, and rows for tenant domains no company has cells in yet.
 */
import { useEffect, useState } from 'react';

import type { Domain, Link, Node } from '../../canvas/types';
import { store } from '../../store/store';
import { attempt } from '../adminData';
import { openAddCompany } from '../../shell/AddCompany';
import { BusyButton } from '../../shell/busy';
import { openExport } from '../ExportDialog';
import { useStore } from '../../shell/dom';
import { api } from '../../api/client';
import {
  bindDialog,
  bulkDeleteDialog,
  deleteDomainDialog,
  deleteNodeDialog,
  deleteRelationDialog,
  editDomainDialog,
  moveDialog,
  newDomainDialog,
  removeCompanyDialog,
  renameDialog,
  unbindDialog,
} from '../actions';
import { List, type Column } from '../List';
import { en } from '../listModel';
import { Tg } from '../Toggle';

const HOST_STYLE = { height: 'calc(100% - 80px)' };
const ACT = (w: number) => ({ width: `${w}px`, textAlign: 'center' as const });

/** A set of picked row keys that empties whenever the portal re-renders from scratch. */
function usePicked<K>(rev: number): [Set<K>, (k: K, on: boolean) => void, () => void] {
  const [picked, setPicked] = useState<Set<K>>(() => new Set());
  useEffect(() => setPicked(new Set()), [rev]);
  const pick = (k: K, on: boolean) =>
    setPicked((cur) => {
      const next = new Set(cur);
      if (on) next.add(k);
      else next.delete(k);
      return next;
    });
  return [picked, pick, () => setPicked(new Set())];
}

/** Opens the bulk deletion for picked rows of one company; a pick across companies is explained, not sent. */
function deletePicked(concepts: Node[], products: Domain[]): Promise<void> {
  const companies = [...new Set([...concepts.map((n) => n.company), ...products.map((d) => d.company)])];
  if (!concepts.length && !products.length) return Promise.resolve();
  if (companies.length > 1 || !companies[0]) {
    store.toast2('One company at a time', 'a bulk deletion covers the cells of one company');
    return Promise.resolve();
  }
  return bulkDeleteDialog(companies[0], concepts, products);
}

interface EntityRow extends Record<string, unknown> {
  id: number;
  n: Node;
  name: string;
  company: string;
  domain: string;
  state: string;
  rels: number;
  kind: string;
  bound: string;
}

export function Entities() {
  const st = useStore();
  const { nodes, links } = st.s;
  const [picked, pick] = usePicked<number>(st.ui.adminRev);
  const rows: EntityRow[] = nodes
    .filter((n) => n.kind === 'concept' && !n.dying)
    .map((n) => ({
      id: n.id,
      n,
      name: n.label,
      company: n.company?.name || '',
      domain: n.domain ? n.domain.name : '—',
      state: n.pending ? 'awaiting approval' : n.sub && /certified/.test(n.sub) ? 'certified' : 'approved',
      rels: links.filter((l) => (l.a === n || l.b === n) && l.kind !== 'bind' && !l.dying).length,
      kind: links.some((l) => l.a === n && l.kind === 'isa') ? 'specialisation' : 'concept',
      bound: n.bound ? n.bound.source.label : '—',
    }));
  const columns: Column[] = [
    { label: 'Select', w: '32px', ox: true },
    { label: 'Entity', key: 'name' },
    { label: 'Kind', key: 'kind' },
    { label: 'Company', key: 'company' },
    { label: 'Domain product', key: 'domain' },
    { label: 'State', key: 'state' },
    { label: 'Relations', key: 'rels', num: true },
    { label: 'Bound to', key: 'bound' },
    { label: '', w: '300px' },
  ];
  const chosen = rows.filter((r) => picked.has(r.id)).map((r) => r.n);
  return (
    <>
      <h2>Entities</h2>
      <p className="lead">
        Every concept in the tenant. Open one on the canvas, rename it, or delete it; renames and deletions are proposals like everything else.
      </p>
      <div className="lst-host" id="lstEntities" style={HOST_STYLE}>
        <List
          key={st.ui.adminRev}
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          searchKeys={['name', 'company', 'domain', 'kind', 'bound']}
          filterKey="company"
          pageSize={40}
          extra={
            <BusyButton className="btn danger" id="entDeleteSelected" disabled={!chosen.length} onClick={() => deletePicked(chosen, [])}>
              {`Delete selected (${chosen.length})`}
            </BusyButton>
          }
          renderRow={(r) => (
            <>
              <td data-ox-new="">
                <input
                  type="checkbox"
                  aria-label={`Select ${r.name}`}
                  checked={picked.has(r.id)}
                  disabled={r.state === 'awaiting approval'}
                  onChange={(e) => pick(r.id, e.target.checked)}
                />
              </td>
              <td>
                <b>{r.name}</b>
              </td>
              <td>{r.kind}</td>
              <td>{r.company}</td>
              <td>{r.domain}</td>
              <td>
                <span className={`st ${r.state === 'awaiting approval' ? 'pend' : ''}`}>
                  <i></i>
                  {r.state}
                </span>
              </td>
              <td className="num">{r.rels}</td>
              <td>{r.bound}</td>
              <td className="act">
                <button data-fn="open" style={ACT(54)} onClick={() => st.goTo(r.n)}>
                  Open
                </button>
                <button
                  data-fn="lineage"
                  style={ACT(64)}
                  onClick={() => {
                    st.goTo(r.n);
                    st.showLineage(r.n);
                  }}
                >
                  Lineage
                </button>
                <button data-fn="rename" style={ACT(66)} onClick={() => renameDialog(r.n)}>
                  Rename
                </button>
                <button data-fn="move" data-ox-new="" style={ACT(54)} disabled={r.state === 'awaiting approval'} onClick={() => moveDialog(r.n)}>
                  Move
                </button>
                <button className="danger" data-fn="del" style={ACT(64)} onClick={() => deleteNodeDialog(r.n)}>
                  Delete
                </button>
              </td>
            </>
          )}
          footer={(l) => `${l.filter((r) => r.bound !== '—').length} bound · ${l.filter((r) => r.state === 'awaiting approval').length} pending`}
        />
      </div>
    </>
  );
}

const KIND_TEXT: Record<string, string> = { rel: 'relation', isa: 'is a', same: 'equivalence', clash: 'conflict' };

interface RelationRow extends Record<string, unknown> {
  id: number;
  l: Link;
  name: string;
  subject: string;
  action: string;
  object: string;
  kind: string;
  company: string;
  scope: string;
  state: string;
}

export function Relationships() {
  const st = useStore();
  const rows: RelationRow[] = st.s.links
    .filter((l) => l.kind !== 'bind' && !l.dying)
    .map((l, i) => {
      const ad = l.a.domain,
        bd = l.b.domain;
      return {
        id: i,
        l,
        name: `${l.a.label} ${l.label} ${l.b.label}`,
        subject: l.a.label,
        action: l.label,
        object: l.b.label,
        kind: KIND_TEXT[l.kind] || l.kind,
        company: l.a.company === l.b.company ? l.a.company?.name || '' : `${l.a.company?.name} ↔ ${l.b.company?.name}`,
        scope: ad === bd ? (ad ? ad.name : 'company') : `${ad ? ad.name : 'company'} → ${bd ? bd.name : 'company'}`,
        state: l.pending ? 'awaiting approval' : 'approved',
      };
    });
  const columns: Column[] = [
    { label: 'Subject', key: 'subject' },
    { label: 'Action', key: 'action' },
    { label: 'Object', key: 'object' },
    { label: 'Kind', key: 'kind' },
    { label: 'Company', key: 'company' },
    { label: 'Scope', key: 'scope' },
    { label: 'State', key: 'state' },
    { label: '', w: '200px' },
  ];
  return (
    <>
      <h2>Relationships</h2>
      <p className="lead">Every line in the model, as subject, action, object. Edit changes the action or the direction; both go through approval.</p>
      <div className="lst-host" id="lstRelations" style={HOST_STYLE}>
        <List
          key={st.ui.adminRev}
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          searchKeys={['subject', 'action', 'object', 'kind', 'company', 'scope']}
          filterKey="kind"
          pageSize={40}
          renderRow={(r) => (
            <>
              <td>
                <b>{r.subject}</b>
              </td>
              <td>
                <em style={{ color: 'var(--ink-2)', fontStyle: 'normal' }}>{r.action}</em>
              </td>
              <td>
                <b>{r.object}</b>
              </td>
              <td>{r.kind}</td>
              <td>{r.company}</td>
              <td>{r.scope}</td>
              <td>
                <span className={`st ${r.state === 'awaiting approval' ? 'pend' : ''}`}>
                  <i></i>
                  {r.state}
                </span>
              </td>
              <td className="act">
                <button
                  data-fn="edit"
                  style={ACT(64)}
                  disabled={r.kind === 'conflict'}
                  onClick={() => {
                    st.closeAdmin();
                    const v = st.renderer?.v;
                    st.openLinkBox(r.l.a, r.l.b, (v ? v.W : innerWidth) * 0.4, (v ? v.H : innerHeight) * 0.4, r.l);
                  }}
                >
                  Edit
                </button>
                <button className="danger" data-fn="del" style={ACT(64)} disabled={r.kind === 'conflict'} onClick={() => deleteRelationDialog(r.l, r.name)}>
                  Delete
                </button>
              </td>
            </>
          )}
          footer={(l) => `${l.filter((r) => r.state === 'awaiting approval').length} pending`}
        />
      </div>
    </>
  );
}

interface BindingRow extends Record<string, unknown> {
  id: number;
  n: Node;
  name: string;
  company: string;
  domain: string;
  source: string;
  records: number;
  fresh: string;
  attrs: number;
  pendingAttrs: number;
  state: string;
}

export function Bindings() {
  const st = useStore();
  const rows: BindingRow[] = st.s.nodes
    .filter((n) => n.kind === 'concept' && !n.dying && !n.pending)
    .map((n) => ({
      id: n.id,
      n,
      name: n.label,
      company: n.company?.name || '',
      domain: n.domain ? n.domain.name : '—',
      source: n.bound ? n.bound.source.label : '—',
      records: n.bound ? n.bound.records : 0,
      fresh: n.bound ? n.bound.fresh : '—',
      attrs: (n.attrs || []).filter((a) => a.state === 'approved').length,
      pendingAttrs: (n.attrs || []).filter((a) => a.state !== 'approved').length,
      state: n.bound ? 'bound' : 'no data',
    }));
  const columns: Column[] = [
    { label: 'Entity', key: 'name' },
    { label: 'Company', key: 'company' },
    { label: 'Domain product', key: 'domain' },
    { label: 'Source', key: 'source' },
    { label: 'Records', key: 'records', num: true },
    { label: 'Fresh', key: 'fresh' },
    { label: 'Attributes', key: 'attrs', num: true },
    { label: 'State', key: 'state' },
    { label: '', w: '240px' },
  ];
  return (
    <>
      <h2>Bindings</h2>
      <p className="lead">
        Which entities have data behind them, from which system, how fresh, and how many attributes. Bind and unbind here; both are proposals.
      </p>
      <div className="lst-host" id="lstBindings" style={HOST_STYLE}>
        <List
          key={st.ui.adminRev}
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          searchKeys={['name', 'company', 'domain', 'source']}
          filterKey="state"
          pageSize={40}
          renderRow={(r) => (
            <>
              <td>
                <b>{r.name}</b>
              </td>
              <td>{r.company}</td>
              <td>{r.domain}</td>
              <td>{r.source}</td>
              <td className="num">{r.records ? en(r.records) : '—'}</td>
              <td>{r.fresh}</td>
              <td className="num">
                {r.pendingAttrs ? `${r.attrs} ` : r.attrs}
                {r.pendingAttrs ? <span style={{ color: '#d6bd8a' }}>{`+${r.pendingAttrs}`}</span> : null}
              </td>
              <td>
                <span className={`st ${r.state === 'bound' ? '' : 'off'}`}>
                  <i></i>
                  {r.state}
                </span>
              </td>
              <td className="act">
                <button data-fn="attrs" style={ACT(80)} onClick={() => st.goTo(r.n)}>
                  Attributes
                </button>
                {r.state === 'bound' ? (
                  <button className="danger" data-fn="unbind" style={ACT(70)} onClick={() => unbindDialog(r.n, r.source, r.attrs)}>
                    Unbind
                  </button>
                ) : (
                  <button data-fn="bind" style={ACT(70)} onClick={() => bindDialog(r.n)}>
                    Bind
                  </button>
                )}
              </td>
            </>
          )}
          footer={(l) => `${l.filter((r) => r.state === 'bound').length} bound · ${en(l.reduce((a, r) => a + r.records, 0))} records`}
        />
      </div>
    </>
  );
}

export function Companies() {
  const st = useStore();
  const { companies, nodes, links } = st.s;
  return (
    <>
      <h2>Companies</h2>
      <p className="lead">
        Each company is its own business-as-a-product: its domain products, owners, vocabulary and sources. Nothing is merged between companies;
        alignment is explicit.
      </p>
      <table className="tbl">
        <thead>
          <tr>
            <th>Company</th>
            <th>Context</th>
            <th>Domain products</th>
            <th>Concepts</th>
            <th>Sources</th>
            <th>Equivalences</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {companies.map((c, i) => (
            <tr key={c.key}>
              <td>
                <b>{c.name}</b>
              </td>
              <td>{c.sub || '—'}</td>
              <td>{c.domains.filter((d) => nodes.some((n) => n.domain === d)).length}</td>
              <td>{nodes.filter((n) => n.company === c && n.kind === 'concept').length}</td>
              <td>{nodes.filter((n) => n.company === c && n.kind === 'source').length}</td>
              <td>{links.filter((l) => l.kind === 'same' && (l.a.company === c || l.b.company === c)).length}</td>
              <td className="act">
                {i > 0 ? (
                  <BusyButton className="danger" data-act="removeCompany" data-id={i} onClick={() => removeCompanyDialog(c)}>
                    Remove
                  </BusyButton>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: '12px', display: st.ui.settings?.companyCreation === false ? 'none' : undefined }}>
        <button className="btn primary" data-act="addCompany" onClick={() => openAddCompany()}>
          + Add a company
        </button>
        <button className="btn" data-ox-new="" data-act="export" style={{ marginLeft: '8px' }} onClick={() => openExport()}>
          Export
        </button>
      </div>
    </>
  );
}

export function DomainProducts() {
  const st = useStore();
  const { DOMAINS, nodes } = st.s;
  const [picked, pick] = usePicked<string>(st.ui.adminRev);
  const shown = DOMAINS.filter((d) => nodes.some((n) => n.domain === d));
  const chosen = shown.filter((d) => d.sid && picked.has(d.sid));
  const tenant = (d: Domain) => st.ui.domains.find((t) => t.key === d.key);
  /** Tenant domains no company has cells in: shown as owner-addition rows so they can be edited. */
  const idle = st.ui.domains.filter((t) => !shown.some((d) => d.key === t.key));
  return (
    <>
      <h2>Domain products</h2>
      <p className="lead">Owned, versioned slices of each company. The version increments on every approved change.</p>
      <table className="tbl">
        <thead>
          <tr>
            <th data-ox-new="" style={{ width: '32px' }}>
              Select
            </th>
            <th>Company</th>
            <th>Domain product</th>
            <th>Owner</th>
            <th>Version</th>
            <th>Concepts</th>
            <th>Bound</th>
            <th>Visible</th>
            <th data-ox-new=""></th>
          </tr>
        </thead>
        <tbody>
          {shown.map((d) => {
            const ms = nodes.filter((n) => n.domain === d && !n.dying);
            const td = tenant(d);
            return (
              <tr key={`${d.company.key}:${d.key}`}>
                <td data-ox-new="">
                  <input
                    type="checkbox"
                    aria-label={`Select ${d.name} of ${d.company.name}`}
                    checked={!!d.sid && picked.has(d.sid)}
                    disabled={!d.sid}
                    onChange={(e) => d.sid && pick(d.sid, e.target.checked)}
                  />
                </td>
                <td>{d.company.name}</td>
                <td>
                  <b style={{ color: d.color }}>{d.name}</b>
                </td>
                <td>{d.owner}</td>
                <td>{`v${d.version.toFixed(1)}`}</td>
                <td>{ms.length}</td>
                <td>{ms.filter((n) => n.bound).length}</td>
                <td style={{ width: '100px' }}>
                  <Tg
                    on={!d.hidden}
                    data-act="domVis"
                    onClick={() => toggleDomainVisible(d)}
                  />
                </td>
                <td className="act" data-ox-new="">
                  <button data-fn="editDomain" style={ACT(54)} disabled={!td} onClick={() => td && editDomainDialog(td)}>
                    Edit
                  </button>
                  <BusyButton className="danger" data-fn="delDomain" style={ACT(64)} disabled={!d.sid} onClick={() => deleteDomainDialog(d)}>
                    Delete
                  </BusyButton>
                </td>
              </tr>
            );
          })}
          {idle.map((t) => (
            <tr key={`tenant:${t.key}`} data-ox-new="">
              <td></td>
              <td>—</td>
              <td>
                <b style={{ color: t.color }}>{t.name}</b>
              </td>
              <td>{t.owner}</td>
              <td>—</td>
              <td>0</td>
              <td>0</td>
              <td style={{ width: '100px' }}></td>
              <td className="act">
                <button data-fn="editDomain" style={ACT(54)} onClick={() => editDomainDialog(t)}>
                  Edit
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div data-ox-new="" style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
        <button className="btn primary" data-act="newDomain" onClick={() => newDomainDialog()}>
          + New domain
        </button>
        <BusyButton className="btn danger" id="domDeleteSelected" disabled={!chosen.length} onClick={() => deletePicked([], chosen)}>
          {`Delete selected (${chosen.length})`}
        </BusyButton>
      </div>
    </>
  );
}

/** Shows or hides a domain product at once; a refusal puts it back and shows the toast. */
export function toggleDomainVisible(d: Domain): void {
  d.hidden = !d.hidden;
  store.renderAdmin();
  const sid = d.sid;
  if (!sid) return;
  const want = d.hidden;
  void attempt(() => api.updateDomainProduct(sid, { hidden: want })).then((r) => {
    if (r !== null) return;
    d.hidden = !want;
    store.renderAdmin();
  });
}
