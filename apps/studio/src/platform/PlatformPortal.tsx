/**
 * The platform portal, a super admin's home when no support session is open: the reference's
 * admin window with the title `Ontology Builder platform`, one nav group `Platform` (Organizations,
 * Platform audit log) and `#adminAccount`. It has no × button, because there is nothing behind it.
 */
import { useState } from 'react';

import { AccountControls } from '../auth/AccountControls';
import { useT, type MessageKey } from '../i18n/i18n';
import { Dialog } from '../shell/Dialog';
import { useTableCellLabels } from '../shell/tableCellLabels';
import { Toasts } from '../shell/Toasts';
import { Organizations } from './Organizations';
import { PlatformAudit } from './PlatformAudit';

type PlatformPage = 'organizations' | 'audit';

const NAV: [PlatformPage, MessageKey][] = [
  ['organizations', 'platform.nav.organizations'],
  ['audit', 'platform.nav.audit'],
];

export function PlatformPortal() {
  const t = useT();
  const [page, setPage] = useState<PlatformPage>('organizations');
  useTableCellLabels();
  return (
    <>
      <Toasts />
      <div className="admin on" id="platform" aria-labelledby="platformTitle">
        <div className="win">
          <div className="head">
            <div id="platformTitle">{t('platform.title')}</div>
            <AccountControls />
          </div>
          <nav id="platformNav">
            <div className="grp">{t('platform.nav.group')}</div>
            {NAV.map(([key, label]) => (
              <button key={key} data-page={key} className={page === key ? 'on' : ''} onClick={() => setPage(key)}>
                {t(label)}
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
