/**
 * The Data group of the admin portal: Data sources and Connectors (`pageSources`,
 * `pageConnectors`, reference lines 1010-1012; actions from `adminAction`, line 1037).
 */
import { useState } from 'react';

import { api } from '../../api/client';
import { useStore } from '../../shell/dom';
import { attempt } from '../adminData';
import { removeSourceDialog, renderAdmin, toggleSource } from '../actions';
import { en } from '../listModel';
import { showSourceForm } from '../SourceWizard';
import { Tg } from '../Toggle';

/** How long the Refresh all button spins before the counts are re-read, in milliseconds. */
const REFRESH_SPIN_MS = 900;

export function DataSources() {
  const st = useStore();
  const [refreshing, setRefreshing] = useState(false);
  const { nodes, links } = st.s;
  const src = nodes.filter((n) => n.kind === 'source');
  const refreshAll = () => {
    setRefreshing(true);
    setTimeout(() => {
      void attempt(() => api.refreshAllSources()).then((r) => {
        setRefreshing(false);
        if (!r) return;
        st.toast2('Refreshed', 'counts and schemas re-read');
        renderAdmin();
      });
    }, REFRESH_SPIN_MS);
  };
  return (
    <>
      <h2>Data sources</h2>
      <p className="lead">
        Systems connected to this tenant, what they feed, and their state. Adding one proposes it; it feeds nothing until an owner approves the binding.
      </p>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
        <button className="btn primary" data-act="add" onClick={() => showSourceForm(null)}>
          + Add a data source
        </button>
        <button className="btn" data-act="refreshAll" onClick={refreshAll}>
          {refreshing ? (
            <>
              <span className="spin"></span>Refreshing
            </>
          ) : (
            'Refresh all'
          )}
        </button>
      </div>
      <table className="tbl">
        <thead>
          <tr>
            <th>Source</th>
            <th>Type</th>
            <th>Company</th>
            <th>Feeds</th>
            <th>Records</th>
            <th>State</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {src.length ? (
            src.map((n) => {
              const b = links.filter((l) => l.kind === 'bind' && l.a === n && !l.pending);
              const rec = b.reduce((a, l) => a + (l.b.bound ? l.b.bound.records : 0), 0);
              const cls = n.pending ? 'pend' : n.disabled ? 'off' : '';
              return (
                <tr key={n.id}>
                  <td>
                    <b>{n.label}</b>
                  </td>
                  <td>{n.sub}</td>
                  <td>{n.company?.name}</td>
                  <td>{`${b.length} concept${b.length === 1 ? '' : 's'}`}</td>
                  <td>{rec ? en(rec) : '—'}</td>
                  <td>
                    <span className={`st ${cls}`}>
                      <i></i>
                      {n.pending ? 'awaiting approval' : n.disabled ? 'disabled' : 'connected · fresh'}
                    </span>
                  </td>
                  <td className="act" style={{ width: '290px' }}>
                    <button data-act="configure" style={{ width: '86px', textAlign: 'center' }} onClick={() => showSourceForm(n)}>
                      Configure
                    </button>
                    <Tg on={!n.disabled && !n.pending} locked={n.pending} data-act="toggle" onClick={() => toggleSource(n)} />
                    <button className="danger" data-act="remove" style={{ width: '70px', textAlign: 'center' }} onClick={() => removeSourceDialog(n)}>
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })
          ) : (
            <tr>
              <td colSpan={7} style={{ color: 'var(--ink-3)' }}>
                No data source yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <div id="srcForm"></div>
    </>
  );
}

export function Connectors() {
  const st = useStore();
  return (
    <>
      <h2>Connectors</h2>
      <p className="lead">
        Connector types available to this tenant. Each one reads schemas, record counts and freshness; none writes back. Add one to configure a data
        source.
      </p>
      <div className="cat">
        {st.ui.connectors.map((c) => (
          <div className="c" key={c.code}>
            <b>
              <i>{c.code}</i>
              {c.name}
            </b>
            <small>{`${c.category} · ${c.scopeText}`}</small>
            <button
              className="btn"
              data-act="addType"
              data-id={c.code}
              onClick={() => {
                st.setAdminPage('sources');
                showSourceForm(null, c);
              }}
            >
              Add
            </button>
          </div>
        ))}
      </div>
    </>
  );
}
