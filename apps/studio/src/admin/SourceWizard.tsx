/**
 * The data-source wizard: connector, configure, verify and propose. Markup and behaviour from
 * `showSourceForm` in reference/ontaix-studio-reference.html lines 1055-1068. Configuring an
 * existing source opens it at step 2; saving is immediate, a new source is a proposal.
 */
import { Fragment, useEffect, useRef, useState } from 'react';

import { api } from '../api/client';
import type { ConnectorType, Discovery, RefreshInterval, Source, SourceAuth } from '../api/types';
import type { Node } from '../canvas/types';
import { BusyButton } from '../shell/busy';
import { DialogFrame } from '../shell/Dialog';
import { store } from '../store/store';
import { attempt, failed } from './adminData';
import { renderAdmin } from './actions';
import { en } from './listModel';

const AUTHS: [string, SourceAuth][] = [
  ['Service principal (Entra ID)', 'service_principal'],
  ['OAuth 2.0 client credentials', 'oauth2_client_credentials'],
  ['Managed identity', 'managed_identity'],
  ['API key from Key Vault', 'key_vault_api_key'],
];
const REFRESH: RefreshInterval[] = ['5 min', '15 min', '1 h', 'daily'];

/** Wait before the verification result appears, in milliseconds. */
const VERIFY_MS = 1100;

/** The catalogue name without its ` ·` or ` (` qualifier, the default display name. */
export const shortName = (c: ConnectorType): string => c.name.split(' ·')[0].split(' (')[0];

/**
 * Opens the wizard: a new source at step 1, an existing one at step 2 with its stored
 * connection settings. When those cannot be read, only the refusal toast shows: an edit form
 * opened with blanks would overwrite the real configuration on save.
 */
export function showSourceForm(n: Node | null, cat: ConnectorType | null = null): Promise<void> {
  if (!n) {
    store.openDialog({ render: (close) => <SourceWizard n={null} src={null} cat={cat} close={close} /> });
    return Promise.resolve();
  }
  const sid = n.sid;
  if (!sid) return Promise.resolve();
  return api.getSource(sid).then(
    (src) => {
      store.openDialog({ render: (close) => <SourceWizard n={n} src={src} cat={null} close={close} /> });
    },
    (err: unknown) => failed(err, 'Unavailable'),
  );
}

interface Data {
  name: string;
  co: number;
  host: string;
  auth: string;
  scope: string;
  refresh: RefreshInterval;
}

function SourceWizard({ n, src, cat, close }: { n: Node | null; src: Source | null; cat: ConnectorType | null; close: () => void }) {
  const catalog = store.ui.connectors;
  const companies = store.s.companies;
  const [step, setStep] = useState(n ? 2 : 1);
  const [sel, setSel] = useState<ConnectorType | null>(cat || (src ? catalog.find((c) => c.code === src.connectorCode) || null : null));
  const [q, setQ] = useState('');
  const [data, setData] = useState<Data>(() => ({
    name: n ? n.label : cat ? shortName(cat) : '',
    co: n && n.company ? Math.max(0, companies.indexOf(n.company)) : 0,
    host: src?.host || '',
    auth: (AUTHS.find((a) => a[1] === src?.auth) || AUTHS[0])[0],
    scope: src?.scope || '',
    refresh: src?.refresh || store.ui.settings?.refresh || '15 min',
  }));
  const [found, setFound] = useState<Discovery | null>(null);
  const [error, setError] = useState<string | null>(null);
  const search = useRef<HTMLInputElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const alive = useRef(true);

  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );
  useEffect(() => {
    if (step === 1) search.current?.focus();
  }, [step]);

  const set = (patch: Partial<Data>) => setData((d) => ({ ...d, ...patch }));

  /** Step 3: verification runs after a pause whatever happens to the dialog meanwhile, as in the reference. */
  const verify = (d: Data, connector: ConnectorType | null) => {
    setFound(null);
    setError(null);
    const auth = (AUTHS.find((a) => a[0] === d.auth) || AUTHS[0])[1];
    setTimeout(() => {
      void api
        .discover(connector ? connector.code : 'schema', { host: d.host, scope: d.scope, auth, displayName: d.name })
        .then(
          (r) => {
            if (alive.current) setFound(r);
          },
          (err: unknown) => {
            if (!alive.current) return;
            setError(err instanceof Error ? err.message : 'Verification failed');
          },
        );
    }, VERIFY_MS);
  };

  const next = () => {
    if (step === 1) {
      if (!sel) return;
      setStep(2);
      return;
    }
    if (step === 2) {
      if (!data.name.trim()) {
        nameInput.current?.focus();
        return;
      }
      const d = { ...data, name: data.name.trim(), host: data.host.trim(), scope: data.scope.trim() };
      setData(d);
      setStep(3);
      verify(d, sel);
      return;
    }
    return finish();
  };

  /** Saves or proposes the source; the wizard closes once the calls settle. */
  const finish = (): Promise<void> => {
    const co = companies[data.co] || companies[0];
    const auth = (AUTHS.find((a) => a[0] === data.auth) || AUTHS[0])[1];
    if (n) {
      const sid = n.sid;
      if (!sid) {
        close();
        return Promise.resolve();
      }
      const saved = attempt(() => api.updateSource(sid, { host: data.host, scope: data.scope, auth, refresh: data.refresh })).then((r) => {
        if (!r) return;
        store.toast2('Saved', `${data.name} reconfigured`);
        renderAdmin();
      });
      const renamed =
        data.name !== n.label
          ? store
              .propose({ type: 'change', changeKind: 'rename_source', payload: { sourceId: sid, newLabel: data.name } })
              .then((p) => {
                if (p) store.toast2('Proposed', `rename to ${data.name}`);
              }, failed)
          : undefined;
      return Promise.all([saved, renamed]).then(close);
    }
    if (!co?.sid) {
      close();
      return Promise.resolve();
    }
    return store
      .propose({
        type: 'source',
        companyId: co.sid,
        label: data.name,
        kindText: sel ? sel.category : 'system',
        ...(sel ? { connectorCode: sel.code } : {}),
        host: data.host,
        scope: data.scope,
        auth,
        refresh: data.refresh,
        caption: `${data.name} is connected to ${co.name} as a read-only source. Bind concepts to it from the canvas: drop a cell on it.`,
      })
      .then((p) => {
        if (!p) return;
        store.toast2('Proposed', `${data.name} is waiting for approval on the canvas`);
        if (store.ui.adminOpen) renderAdmin();
        store.caption('One proposal', `${data.name} (${sel ? sel.name : 'system'}) is waiting for approval as a data source of ${co.name}.`);
      }, failed)
      .then(close);
  };

  const steps = (
    <div className="steps">
      <span className={step === 1 ? 'on' : 'done'}>
        <i>1</i>Connector
      </span>
      <em></em>
      <span className={step === 2 ? 'on' : step > 2 ? 'done' : ''}>
        <i>2</i>Configure
      </span>
      <em></em>
      <span className={step === 3 ? 'on' : ''}>
        <i>3</i>Verify and propose
      </span>
    </div>
  );

  const f = q.toLowerCase();
  const shown = catalog.filter((c) => !f || `${c.name} ${c.category} ${c.scopeText}`.toLowerCase().includes(f));

  return (
    <DialogFrame
      title={n ? `Configure ${n.label}` : 'Add a data source'}
      sub={n ? '' : 'three steps'}
      onClose={close}
      footer={
        <>
          <button className="btn left" data-i={0} style={step > 1 ? undefined : { visibility: 'hidden' }} onClick={() => step > 1 && setStep(step - 1)}>
            Back
          </button>
          <button className="btn " data-i={1} onClick={close}>
            Cancel
          </button>
          <BusyButton className="btn primary" data-i={2} disabled={step === 1 && !sel} onClick={next}>
            {step === 3 ? 'Propose this source' : 'Next'}
          </BusyButton>
        </>
      }
    >
      {/* Each step replaces the whole body, as the reference rewrites it. */}
      <Fragment key={step}>
      {steps}
      {step === 1 ? (
        <>
          <input className="search" id="wzSearch" ref={search} placeholder="Search connectors, e.g. SAP, Fabric, Workday" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="cat" id="wzCat">
            {shown.length ? (
              shown.map((c) => (
                <div
                  key={c.code}
                  className={`c${sel && sel.code === c.code ? ' sel' : ''}`}
                  data-k={c.code}
                  onClick={() => {
                    setSel(c);
                    if (!data.name || !n) set({ name: shortName(c) });
                  }}
                >
                  <b>
                    <i>{c.code}</i>
                    {c.name}
                  </b>
                  <small>{`${c.category} · ${c.scopeText}`}</small>
                </div>
              ))
            ) : (
              <small style={{ color: 'var(--ink-3)' }}>No connector matches.</small>
            )}
          </div>
        </>
      ) : null}
      {step === 2 ? (
        <div className="form">
          <label>Connector</label>
          <div>
            <b>{sel ? sel.name : '—'}</b> <span style={{ color: 'var(--ink-3)' }}>{`· ${sel ? sel.scopeText : ''}`}</span>
          </div>
          <label>Display name</label>
          <input id="wzName" ref={nameInput} value={data.name} placeholder="e.g. SAP ERP Europe" onChange={(e) => set({ name: e.target.value })} />
          <label>Company</label>
          <select id="wzCo" value={data.co} onChange={(e) => set({ co: +e.target.value })}>
            {companies.map((c, i) => (
              <option key={c.key} value={i}>
                {c.name}
              </option>
            ))}
          </select>
          <label>Host or workspace</label>
          <input id="wzHost" value={data.host} placeholder="sap-prod.northwind.local · workspace id · account" onChange={(e) => set({ host: e.target.value })} />
          <label>Authentication</label>
          <select id="wzAuth" value={data.auth} onChange={(e) => set({ auth: e.target.value })}>
            {AUTHS.map(([label]) => (
              <option key={label}>{label}</option>
            ))}
          </select>
          <label>Scope</label>
          <input id="wzScope" value={data.scope} placeholder="schemas, tables or objects to read · blank = discover" onChange={(e) => set({ scope: e.target.value })} />
          <label>Refresh</label>
          <select id="wzRefresh" value={data.refresh} onChange={(e) => set({ refresh: e.target.value as RefreshInterval })}>
            {REFRESH.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
          <label></label>
          <small style={{ color: 'var(--ink-3)' }}>Read-only. Ontology Builder never writes into a source system.</small>
        </div>
      ) : null}
      {step === 3 ? (
        <div id="wzTest">
          {found ? (
            <>
              <div style={{ color: 'var(--good)', marginBottom: '8px' }}>{found.statusText}</div>
              <div className="discover">
                {found.objects.map((o, i) => (
                  <div key={i}>
                    {o.name}
                    <span>{`${en(o.rows)} rows`}</span>
                  </div>
                ))}
              </div>
              <p style={{ margin: '12px 0 0', color: 'var(--ink-3)' }}>
                Proposing this source adds <b style={{ color: 'var(--ink)' }}>{data.name}</b>
                {' to '}
                <b style={{ color: 'var(--ink)' }}>{(companies[data.co] || companies[0])?.name}</b>
                {' on the canvas, awaiting approval. Bind concepts to it by dropping a cell on it.'}
              </p>
            </>
          ) : error ? (
            <div style={{ color: 'var(--conflict)' }}>{error}</div>
          ) : (
            <>
              <span className="spin"></span>Connecting to <b>{data.name}</b>
              {` as ${data.auth.toLowerCase()}…`}
            </>
          )}
        </div>
      ) : null}
      </Fragment>
    </DialogFrame>
  );
}
