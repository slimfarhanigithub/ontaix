/**
 * Wordmark, listening status, admin button and the "Show changes" button that appears while the
 * panel is hidden. Markup from reference/ontaix-studio-reference.html lines 186-190, without the
 * scene counter and scene name. "Show changes" sits in the header row after the admin button, in
 * the same style, so the two never overlap when the panel's width goes to 0.
 */
import { useAuth } from '../auth/authStore';
import { refStyle, useStore } from './dom';

export function Header() {
  const st = useStore();
  const { session } = useAuth();
  const { proposals, listening } = st.ui;
  // A super admin's support session shows the organization read-only; the pill says so for its whole life.
  const support = session?.support ?? null;
  return (
    <>
      <header>
        <div>
          <div className="wordmark">
            <i></i>Ontology Builder <small>business as a product</small>
          </div>
          <div className={`status${listening || support ? ' on' : ''}`} id="status">
            <i></i>
            <span>{support ? `Support · ${support.organization.name} · read-only` : 'Listening'}</span>
          </div>
        </div>
        <div className="scene">
          <div ref={refStyle('margin-top:6px;text-align:right;pointer-events:auto')}>
            <button className="admin-open" id="adminOpen" title="Administration portal (G)" onClick={() => st.openAdmin()}>
              <svg viewBox="0 0 16 16">
                <circle cx="8" cy="8" r="2.2" />
                <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" />
              </svg>
              Admin portal
            </button>
            <button
              className="admin-open"
              id="panelShow"
              ref={refStyle('display:none')}
              title="Show the changes panel (P)"
              onClick={() => st.togglePanel()}
            >
              {`Show changes${proposals.length ? ' (' + proposals.length + ')' : ''}`}
            </button>
          </div>
        </div>
      </header>
    </>
  );
}
