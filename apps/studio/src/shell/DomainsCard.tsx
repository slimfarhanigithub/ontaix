/**
 * The domain products card and its toggle. Markup from reference/ontaix-studio-reference.html
 * lines 222-223; behaviour from `renderDomains` (lines 621-632) and `toggleDomainsCard`
 * (lines 552-554). The toggle and the card stack in the left-hand dock (`.dock-l`), which keeps
 * the toggle 8 px above the card as `placeDomainsToggle` does, without measuring.
 */
import { liveOf } from '../canvas/state';
import { themedColour } from '../design/tokens';
import { useT } from '../i18n/i18n';
import { refStyle, useStore } from './dom';

export function DomainsCard() {
  const st = useStore();
  const t = useT();
  const s = st.s;
  const off = st.ui.domainsOff;
  const allOn = s.DOMAINS.every((d) => !d.hidden);
  return (
    <div className="dock-l">
      <button
        className="legend-toggle"
        id="domainsToggle"
        aria-expanded={!off}
        aria-controls="domains"
        title={t('shell.domains.toggleTitle')}
        onClick={() => st.toggleDomainsCard()}
      >
        {off ? t('shell.domains.show') : t('shell.domains.hide')}
      </button>
      <nav className={`domains${off ? ' off' : ''}`} id="domains" aria-label={t('shell.domains.title')}>
        <div className="title">
          <span>{t('shell.domains.title')}</span>
          <button id="domAll" onClick={() => st.toggleAllDomains()}>
            {allOn ? t('shell.domains.disableAll') : t('shell.domains.enableAll')}
          </button>
        </div>
        {s.companies.map((c) => {
          const live = liveOf(s, c);
          return (
            <CompanyRows key={c.key} live={live} multi={s.companies.length > 1} c={c} />
          );
        })}
      </nav>
    </div>
  );
}

function CompanyRows({
  c,
  live,
  multi,
}: {
  c: ReturnType<typeof useStore>['s']['companies'][number];
  live: ReturnType<typeof liveOf>;
  multi: boolean;
}) {
  const st = useStore();
  const t = useT();
  const s = st.s;
  return (
    <>
      {multi ? (
        <div className="co">
          <span>{c.name}</span>
          <button
            className="sw"
            role="switch"
            aria-checked={live.length && live.every((d) => d.hidden) ? 'false' : 'true'}
            aria-label={t('shell.domains.enable', { name: c.name })}
            onClick={() => st.toggleCompanyDomains(c)}
          ></button>
        </div>
      ) : null}
      {!live.length ? (
        <div className="row">
          <i ref={refStyle('opacity:0')}></i>
          <span ref={refStyle('text-align:left')}>{t('shell.domains.none')}</span>
        </div>
      ) : null}
      {live.map((d) => {
        const cnt = s.nodes.filter((n) => n.domain === d && !n.dying).length;
        const focus = s.focusDomain === d;
        return (
          <div key={d.key} className={'row' + (d.hidden ? ' off' : '')} style={{ color: themedColour(d.color) }}>
            <i></i>
            <button
              className={`name${focus ? ' focus' : ''}`}
              title={focus ? t('shell.domains.showAll') : t('shell.domains.showOne', { name: d.name })}
              onClick={() => st.focusDomainFromCard(d)}
            >
              {d.name}
            </button>
            <span>{cnt || ''}</span>
            <button
              className="sw"
              role="switch"
              aria-checked={d.hidden ? 'false' : 'true'}
              aria-label={t('shell.domains.enable', { name: d.name })}
              onClick={() => st.toggleDomainHidden(d)}
            ></button>
          </div>
        );
      })}
    </>
  );
}
