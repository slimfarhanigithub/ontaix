/**
 * The domain products card and its toggle. Markup from reference/ontaix-studio-reference.html
 * lines 222-223; behaviour from `renderDomains` (lines 621-632) and `toggleDomainsCard`
 * (lines 552-554). The toggle and the card stack in the left-hand dock (`.dock-l`), which keeps
 * the toggle 8 px above the card as `placeDomainsToggle` does, without measuring.
 */
import { liveOf } from '../canvas/state';
import { themedColour } from '../design/tokens';
import { refStyle, useStore } from './dom';

export function DomainsCard() {
  const st = useStore();
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
        title="Show or hide the domain list (D)"
        onClick={() => st.toggleDomainsCard()}
      >
        {off ? 'Show domains' : 'Hide domains'}
      </button>
      <nav className={`domains${off ? ' off' : ''}`} id="domains" aria-label="Domain products">
        <div className="title">
          <span>Domain products</span>
          <button id="domAll" onClick={() => st.toggleAllDomains()}>
            {allOn ? 'disable all' : 'enable all'}
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
            aria-label={`Enable ${c.name}`}
            onClick={() => st.toggleCompanyDomains(c)}
          ></button>
        </div>
      ) : null}
      {!live.length ? (
        <div className="row">
          <i ref={refStyle('opacity:0')}></i>
          <span ref={refStyle('text-align:left')}>no domain products yet</span>
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
              title={focus ? 'Click again to show all' : 'Show ' + d.name + ' with the domain products it relates to'}
              onClick={() => st.focusDomainFromCard(d)}
            >
              {d.name}
            </button>
            <span>{cnt || ''}</span>
            <button
              className="sw"
              role="switch"
              aria-checked={d.hidden ? 'false' : 'true'}
              aria-label={`Enable ${d.name}`}
              onClick={() => st.toggleDomainHidden(d)}
            ></button>
          </div>
        );
      })}
    </>
  );
}
