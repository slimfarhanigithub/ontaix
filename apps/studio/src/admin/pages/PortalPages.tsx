/**
 * The Portal group of the admin portal: Overview, Tenant settings and Appearance
 * (`pageOverview`, `pageSettings`, `pageAppearance`, reference lines 971-984). Every setting row
 * has a description (./rowText adds the ones the reference leaves empty), Appearance holds the
 * user's Skip animation choice under Motion, and owner additions for ontology editing, marked
 * `data-ox-new`: the `Company creation` setting row and a colour input per custom domain in
 * Appearance.
 */
import { DEFAULT_BRASS, DEFAULT_COLORS, DOMAIN_TEMPLATES } from '../../canvas/constants';
import { DEFAULT_ACCENT } from '../../design/tokens';
import { BusyButton } from '../../shell/busy';
import { useStore } from '../../shell/dom';
import { changeColour, changeRefresh, renderAdmin, resetColours } from '../actions';
import { ADDED_DESCRIPTIONS, SKIP_ANIMATION_ROW } from '../rowText';
import { SetRow, Tg } from '../Toggle';

export function Overview() {
  const st = useStore();
  const { nodes, companies } = st.s;
  const src = nodes.filter((n) => n.kind === 'source'),
    bound = nodes.filter((n) => n.bound).length,
    concepts = nodes.filter((n) => n.kind === 'concept').length;
  return (
    <>
      <h2>Overview</h2>
      <p className="lead">What this tenant holds and what is switched on. Everything here is the same model you see on the canvas.</p>
      <div className="kpis">
        <div>
          <b>{companies.length}</b>
          <span>{`compan${companies.length === 1 ? 'y' : 'ies'}`}</span>
        </div>
        <div>
          <b>{concepts}</b>
          <span>{`concepts · ${bound} bound to data`}</span>
        </div>
        <div>
          <b>{src.length}</b>
          <span>{`data sources · ${src.filter((n) => n.pending).length} pending`}</span>
        </div>
        <div>
          <b>{st.ui.proposals.length}</b>
          <span>proposals awaiting approval</span>
        </div>
      </div>
      <h3>Enabled</h3>
      <SetRow
        k="approvalRequired"
        title="Approval on every change"
        desc="Nothing enters the model without an owner’s approval. This is the product’s contract and cannot be switched off."
        locked
      />
      <SetRow k="voice" title="Voice capture" desc="Microphone input in the teaching bar." />
      <SetRow k="importDocs" title="Document import" desc="Text, Markdown, CSV, Word and PDF, read in the browser." />
      <SetRow k="multiCompany" title="Portfolio mode" desc="Several companies in one view." />
      <SetRow k="crossCompany" title="Companies may interact" desc="Relations and equivalences between companies." />
      <SetRow k="agentAccess" title="Agent access through the gateway" desc="Agents read the certified model through MCP." />
    </>
  );
}

const REFRESH = ['5 min', '15 min', '1 h', 'daily'];
const REFRESH_STYLE =
  'font:inherit;font-size:12px;background:var(--surface-2);border:1px solid var(--border-strong);border-radius:8px;padding:6px 8px;color:var(--ink);grid-row:1/3;width:88px;justify-self:end;box-sizing:border-box';

export function TenantSettings() {
  const st = useStore();
  const refresh = st.ui.settings?.refresh || '15 min';
  return (
    <>
      <h2>Tenant settings</h2>
      <p className="lead">Switch capabilities on or off for everyone in this tenant. Changes apply immediately and are written to the audit log.</p>
      <h3>Capture and teaching</h3>
      <SetRow k="liveTeaching" title="Live teaching" desc="Typing or speaking a sentence proposes concepts and relations." />
      <SetRow k="voice" title="Voice input" desc="Use the browser microphone for live teaching." />
      <SetRow k="importDocs" title="Document import" desc="Read documents into proposals." />
      <SetRow k="everyoneTeaches" title="Members can teach" desc="When off, only Builders and Owners can propose; Members can only read." />
      <h3>Governance</h3>
      <SetRow
        k="approvalRequired"
        title="Approval required for every change"
        desc={ADDED_DESCRIPTIONS['Approval required for every change']}
        locked
      />
      <SetRow
        k="twoApprovers"
        title="Two approvers for changes"
        desc="Renames, deletions and conflict resolutions need an Owner and a Governor. A second click is required in the proposals panel."
      />
      <SetRow
        k="autoAttrs"
        title="Auto-approve discovered attributes"
        desc="Attributes read from a bound schema enter the model without review. Recommended off until the connectors are trusted."
      />
      <SetRow k="notifyOwners" title="Notify domain owners" desc="Owners are notified when a proposal lands in their domain product." />
      <h3>Portfolio</h3>
      <SetRow k="multiCompany" title="Several companies in one view" desc={ADDED_DESCRIPTIONS['Several companies in one view']} />
      <SetRow ox k="companyCreation" title="Company creation" desc="Allow adding companies." />
      <SetRow
        k="crossCompany"
        title="Companies may interact"
        desc="Allow relations and equivalences between companies. Disabling removes every existing cross-company relationship; each company keeps its own model intact."
      />
      <h3>Data</h3>
      <SetRow k="readOnlyConnectors" title="Connectors are read-only" desc="Ontaix reads schemas and counts. It never writes into a source system." locked />
      <div className="set">
        <b>Refresh interval</b>
        <select
          id="refreshSel"
          ref={(el) => {
            if (el) el.setAttribute('style', REFRESH_STYLE);
          }}
          value={refresh}
          onChange={(e) => changeRefresh(e.target.value)}
        >
          {REFRESH.map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
        <p>How often record counts and schemas are re-read from bound sources.</p>
      </div>
      <h3>Display</h3>
      <SetRow k="animations" title="Animations" desc="Cell division and line tracing. Off makes changes instant." />
      <SetRow k="coverageDefault" title="Coverage view by default" desc="Open the canvas with data coverage colouring on." />
      <SetRow k="legend" title="Show the relationship legend" desc={ADDED_DESCRIPTIONS['Show the relationship legend']} />
    </>
  );
}

export function Appearance() {
  const st = useStore();
  const ap = st.ui.appearance;
  const colour = (key: string) => ap?.colors[key] || DEFAULT_COLORS[key];
  return (
    <>
      <h2>Appearance</h2>
      <p className="lead">
        Colours apply to every company in the tenant: a domain product keeps the same colour wherever it appears, so companies compare at a glance.
      </p>
      <h3>Domain products</h3>
      <div className="colors">
        {DOMAIN_TEMPLATES.map((t) => (
          <label className="col" key={t.key}>
            <input type="color" value={colour(t.key)} data-col={t.key} onChange={(e) => changeColour(t.key, e.target.value)} />
            <span>
              <b>{st.ui.domains.find((d) => d.key === t.key)?.name ?? t.name}</b>
              <small>{colour(t.key)}</small>
            </span>
          </label>
        ))}
        {st.ui.domains
          .filter((d) => !d.template)
          .map((d) => (
            <label className="col" key={d.key} data-ox-new="">
              <input type="color" value={ap?.colors[d.key] || d.color} data-col={d.key} onChange={(e) => changeColour(d.key, e.target.value)} />
              <span>
                <b>{d.name}</b>
                <small>{ap?.colors[d.key] || d.color}</small>
              </span>
            </label>
          ))}
      </div>
      <h3>Theme</h3>
      <div className="set">
        <b>Light mode</b>
        <Tg
          on={st.ui.theme === 'light'}
          data-act="theme"
          onClick={() => {
            st.toggleTheme();
            renderAdmin();
          }}
        />
        <p>Light interface and canvas. Domain colours stay the same; the company and domain regions adapt.</p>
      </div>
      <h3>{SKIP_ANIMATION_ROW.heading}</h3>
      <div className="set">
        <b>{SKIP_ANIMATION_ROW.title}</b>
        <Tg
          on={st.ui.skipAnimation}
          data-act="skipAnimation"
          onClick={() => {
            st.toggleSkip();
            renderAdmin();
          }}
        />
        <p>{SKIP_ANIMATION_ROW.desc}</p>
      </div>
      <h3>Interface</h3>
      <div className="colors">
        <label className="col">
          <input type="color" value={ap?.accent || DEFAULT_ACCENT} data-col="__accent" onChange={(e) => changeColour('__accent', e.target.value)} />
          <span>
            <b>Accent</b>
            <small>buttons, focus, approvals</small>
          </span>
        </label>
        <label className="col">
          <input type="color" value={ap?.source || DEFAULT_BRASS} data-col="__source" onChange={(e) => changeColour('__source', e.target.value)} />
          <span>
            <b>Data sources</b>
            <small>systems and bindings</small>
          </span>
        </label>
      </div>
      <div style={{ marginTop: '16px' }}>
        <BusyButton className="btn" data-act="resetColors" onClick={resetColours}>
          Reset to defaults
        </BusyButton>
      </div>
    </>
  );
}
