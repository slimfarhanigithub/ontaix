/**
 * The administration portal frame: backdrop, window and header with the theme switch. Markup
 * from reference/ontaix-studio-reference.html line 192; open, close and theme behaviour from
 * lines 948-952. The navigation and the pages come from the admin module.
 */
import { AdminMain, AdminNav } from '../admin/AdminPortal';
import { refStyle, useStore } from './dom';

export function AdminOverlay() {
  const st = useStore();
  const { adminOpen, theme, proposals } = st.ui;
  const sub =
    st.s.companies.map((c) => c.name).join(' · ') +
    (proposals.length ? ` · ${proposals.length} proposal${proposals.length === 1 ? '' : 's'} waiting on the canvas` : '');
  return (
    <div
      className={`admin${adminOpen ? ' on' : ''}`}
      id="admin"
      role="dialog"
      aria-modal="true"
      aria-label="Administration portal"
      onClick={(e) => {
        if (e.target === e.currentTarget) st.closeAdmin();
      }}
    >
      <div className="win">
        <div className="head">
          Ontaix admin portal <span id="adminSub">{sub}</span>
          <button
            className="btn"
            id="themeBtn"
            ref={refStyle('margin-left:auto;display:inline-flex;align-items:center;gap:6px')}
            title="Switch between dark and light mode"
            onClick={() => {
              st.toggleTheme();
              if (st.ui.adminOpen) st.renderAdmin();
            }}
          >
            <svg viewBox="0 0 16 16" ref={refStyle('width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round')}>
              <circle cx="8" cy="8" r="3" />
              <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" />
            </svg>
            <span id="themeLbl">{theme === 'light' ? 'Dark mode' : 'Light mode'}</span>
          </button>
          <button className="x" id="adminClose" aria-label="Close" ref={refStyle('margin-left:8px')} onClick={() => st.closeAdmin()}>
            ×
          </button>
        </div>
        <nav id="adminNav">
          <AdminNav />
        </nav>
        <main id="adminMain">
          <AdminMain />
        </main>
      </div>
    </div>
  );
}
