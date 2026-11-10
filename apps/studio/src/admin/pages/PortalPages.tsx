/**
 * The Portal group of the admin portal: Overview, Tenant settings and Appearance
 * (`pageOverview`, `pageSettings`, `pageAppearance`, reference lines 971-984). Every setting row
 * has a description (./rowText adds the ones the reference leaves empty), Appearance holds the
 * user's Skip animation choice under Motion, and owner additions for ontology editing, marked
 * `data-ox-new`: the `Company creation` setting row and a colour input per custom domain in
 * Appearance. Settings that only govern data sources, connectors, coverage or agents have no row.
 */
import { DEFAULT_COLORS, DOMAIN_TEMPLATES } from '../../canvas/constants';
import { DEFAULT_ACCENT } from '../../design/tokens';
import { t, useT, type MessageKey } from '../../i18n/i18n';
import { BusyButton } from '../../shell/busy';
import { useStore } from '../../shell/dom';
import { changeColour, renderAdmin, resetColours } from '../actions';
import { SetRow, Tg, type SettingKey } from '../Toggle';

export function Overview() {
  const st = useStore();
  const t = useT();
  const { nodes, links, companies } = st.s;
  const concepts = nodes.filter((n) => n.kind === 'concept' && !n.dying).length,
    pending = nodes.filter((n) => n.kind === 'concept' && n.pending && !n.dying).length,
    relations = links.filter((l) => l.kind !== 'bind' && !l.dying).length;
  return (
    <>
      <h2>{t('admin.nav.overview')}</h2>
      <p className="lead">{t('admin.overview.lead')}</p>
      <div className="kpis">
        <div>
          <b>{companies.length}</b>
          <span>{t('admin.overview.companies', { n: companies.length })}</span>
        </div>
        <div>
          <b>{concepts}</b>
          <span>{t('admin.overview.concepts', { pending })}</span>
        </div>
        <div>
          <b>{relations}</b>
          <span>{t('admin.overview.relations')}</span>
        </div>
        <div>
          <b>{st.ui.proposals.length}</b>
          <span>{t('admin.overview.proposals')}</span>
        </div>
      </div>
      <h3>{t('admin.overview.enabled')}</h3>
      <SetRow
        k="approvalRequired"
        title={t('admin.overview.approval.title')}
        desc={t('admin.overview.approval.desc')}
        locked
      />
      <SetRow k="voice" title={t('admin.overview.voice.title')} desc={t('admin.overview.voice.desc')} />
      <SetRow k="importDocs" title={t('admin.overview.importDocs.title')} desc={t('admin.overview.importDocs.desc')} />
      <SetRow k="multiCompany" title={t('admin.overview.multiCompany.title')} desc={t('admin.overview.multiCompany.desc')} />
      <SetRow k="crossCompany" title={t('admin.overview.crossCompany.title')} desc={t('admin.overview.crossCompany.desc')} />
    </>
  );
}

/** A Tenant settings row, its title and description read from the `admin.settings.<k>` keys. */
function SettingRow({ k, locked, ox }: { k: SettingKey; locked?: boolean; ox?: boolean }) {
  return <SetRow k={k} title={t(`admin.settings.${k}.title` as MessageKey)} desc={t(`admin.settings.${k}.desc` as MessageKey)} locked={locked} ox={ox} />;
}

export function TenantSettings() {
  const t = useT();
  return (
    <>
      <h2>{t('admin.nav.settings')}</h2>
      <p className="lead">{t('admin.settings.lead')}</p>
      <h3>{t('admin.settings.capture')}</h3>
      <SettingRow k="liveTeaching" />
      <SettingRow k="voice" />
      <SettingRow k="importDocs" />
      <SettingRow k="everyoneTeaches" />
      <h3>{t('admin.settings.governance')}</h3>
      <SettingRow k="approvalRequired" locked />
      <SettingRow k="twoApprovers" />
      <SettingRow k="notifyOwners" />
      <h3>{t('admin.settings.portfolio')}</h3>
      <SettingRow k="multiCompany" />
      <SettingRow ox k="companyCreation" />
      <SettingRow k="crossCompany" />
      <h3>{t('admin.settings.display')}</h3>
      <SettingRow k="animations" />
      <SettingRow k="legend" />
    </>
  );
}

export function Appearance() {
  const st = useStore();
  const t = useT();
  const ap = st.ui.appearance;
  const colour = (key: string) => ap?.colors[key] || DEFAULT_COLORS[key];
  return (
    <>
      <h2>{t('admin.nav.appearance')}</h2>
      <p className="lead">{t('admin.appearance.lead')}</p>
      <h3>{t('admin.nav.domains')}</h3>
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
      <h3>{t('admin.appearance.motion')}</h3>
      <div className="set">
        <b>{t('admin.appearance.skip.title')}</b>
        <Tg
          on={st.ui.skipAnimation}
          data-act="skipAnimation"
          onClick={() => {
            st.toggleSkip();
            renderAdmin();
          }}
        />
        <p>{t('admin.appearance.skip.desc')}</p>
      </div>
      <h3>{t('admin.appearance.interface')}</h3>
      <div className="colors">
        <label className="col">
          <input type="color" value={ap?.accent || DEFAULT_ACCENT} data-col="__accent" onChange={(e) => changeColour('__accent', e.target.value)} />
          <span>
            <b>{t('admin.appearance.accent')}</b>
            <small>{t('admin.appearance.accentDesc')}</small>
          </span>
        </label>
      </div>
      <div style={{ marginTop: '16px' }}>
        <BusyButton className="btn" data-act="resetColors" onClick={resetColours}>
          {t('admin.appearance.reset')}
        </BusyButton>
      </div>
    </>
  );
}
