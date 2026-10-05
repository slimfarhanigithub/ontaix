/**
 * The platform portal, a super admin's home when no support session is open: the reference's
 * admin window with the title `Ontology Builder platform`, one nav group `Platform` (Organizations,
 * Platform audit log) and `#adminAccount`. It has no × button, because there is nothing behind it.
 */
import { useState } from 'react';

import { AccountControls } from '../auth/AccountControls';
import { Dialog } from '../shell/Dialog';
import { Toasts } from '../shell/Toasts';
import { Organizations } from './Organizations';
import { PlatformAudit } from './PlatformAudit';

type PlatformPage = 'organizations' | 'audit';

const NAV: [PlatformPage, string][] = [
  ['organizations', 'Organizations'],
  ['audit', 'Platform audit log'],
];

export function PlatformPortal() {
  const [page, setPage] = useState<PlatformPage>('organizations');
  return (
    <>
      <Toasts />
      <div className="admin on" id="platform" aria-labelledby="platformTitle">
        <div className="win">
          <div className="head">
            <div id="platformTitle">Ontology Builder platform</div>
            <AccountControls end />
          </div>
          <nav id="platformNav">
            <div className="grp">Platform</div>
            {NAV.map(([key, label]) => (
              <button key={key} data-page={key} className={page === key ? 'on' : ''} onClick={() => setPage(key)}>
                {label}
              </button>
            ))}
          </nav>
          <main id="platformMain">{page === 'organizations' ? <Organizations /> : <PlatformAudit />}</main>
        </div>
      </div>
      <Dialog />
    </>
  );
}
