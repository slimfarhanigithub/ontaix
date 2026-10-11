/**
 * The administration portal frame: backdrop, window and header. Markup from
 * reference/ontaix-studio-reference.html line 192; open and close behaviour from lines 948-952.
 * The navigation and the pages come from the admin module. While it is open, Tab stays inside
 * the window unless a dialog above it holds the focus, and closing it gives focus back to the
 * element that had it before. With a live session the head also holds `#adminAccount` (the
 * account controls) before its ×; without one the × alone sits at the right.
 */
import { useEffect, useRef } from 'react';

import { AdminMain, AdminNav } from '../admin/AdminPortal';
import { AccountControls } from '../auth/AccountControls';
import { useAuth } from '../auth/authStore';
import { trapTab, useFocusReturn } from './Dialog';
import { refStyle, useStore } from './dom';

export function AdminOverlay() {
  const st = useStore();
  const { session } = useAuth();
  const { adminOpen, proposals } = st.ui;
  const sub =
    st.s.companies.map((c) => c.name).join(' · ') +
    (proposals.length ? ` · ${proposals.length} proposal${proposals.length === 1 ? '' : 's'} waiting on the canvas` : '');
  const win = useRef<HTMLDivElement>(null);
  useFocusReturn(adminOpen, win);
  useEffect(() => {
    if (!adminOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab' || document.activeElement?.closest('.dlg-back')) return;
      trapTab(e, win.current);
    };
    addEventListener('keydown', onKey);
    return () => removeEventListener('keydown', onKey);
  }, [adminOpen]);
  return (
    <div
      className={`admin${adminOpen ? ' on' : ''}`}
      id="admin"
      role="dialog"
      aria-modal="true"
      aria-labelledby="adminTitle"
      onClick={(e) => {
        if (e.target === e.currentTarget) st.closeAdmin();
      }}
    >
      <div className="win" ref={win}>
        <div className="head">
          <div id="adminTitle">Ontology Builder admin portal</div> <span id="adminSub">{sub}</span>
          <AccountControls />
          <button className="x" id="adminClose" aria-label="Close" ref={refStyle(`margin-left:${session ? '8px' : 'auto'}`)} onClick={() => st.closeAdmin()}>
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
