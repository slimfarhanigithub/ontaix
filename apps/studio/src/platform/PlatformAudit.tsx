/**
 * The platform audit log, newest first, in the reference's list pattern: When, Who, Action,
 * Organization, What and Result (`ok` or `refused`). The page shows the newest entries the API
 * hands back in one page.
 */
import { useEffect, useState } from 'react';

import { AUDIT_SHOWN, failed } from '../admin/adminData';
import { List, type Column } from '../admin/List';
import { api } from '../api/client';
import type { PlatformAuditEntry } from '../api/types';

interface AuditRow extends Record<string, unknown> {
  id: number;
  at: string;
  when: string;
  who: string;
  action: string;
  organization: string;
  what: string;
  result: 'ok' | 'refused';
}

/** `dd Mon yyyy, hh:mm:ss` in en-GB. */
export const whenText = (iso: string): string =>
  `${new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}, ${new Date(iso).toLocaleTimeString('en-GB')}`;

export function auditRow(e: PlatformAuditEntry): AuditRow {
  return {
    id: e.id,
    at: e.at,
    when: whenText(e.at),
    who: e.actor?.email || '—',
    action: e.action,
    organization: e.organization?.name || '—',
    what: e.what,
    result: e.ok ? 'ok' : 'refused',
  };
}

export function PlatformAudit() {
  const [entries, setEntries] = useState<PlatformAuditEntry[] | null>(null);
  useEffect(() => {
    let live = true;
    api.listPlatformAudit({ page: 1, pageSize: AUDIT_SHOWN }).then(
      (page) => {
        if (live) setEntries(page.items);
      },
      (err: unknown) => {
        failed(err, 'Unavailable');
        if (live) setEntries([]);
      },
    );
    return () => {
      live = false;
    };
  }, []);
  const rows = (entries || []).map(auditRow);
  const columns: Column[] = [
    { label: 'When', key: 'at' },
    { label: 'Who', key: 'who' },
    { label: 'Action', key: 'action' },
    { label: 'Organization', key: 'organization' },
    { label: 'What', key: 'what' },
    { label: 'Result', key: 'result' },
  ];
  return (
    <>
      <h2>Platform audit log</h2>
      <p className="lead">Every sign-in, password, account, organization and support-session event, append-only.</p>
      <div className="lst-host" id="lstPlatformAudit" style={{ height: 'calc(100% - 80px)' }}>
        {entries ? (
          <List
            columns={columns}
            rows={rows}
            rowKey={(r) => r.id}
            searchKeys={['who', 'action', 'organization', 'what']}
            filterKey="result"
            pageSize={40}
            renderRow={(r) => (
              <>
                <td style={{ color: 'var(--ink-3)', fontVariantNumeric: 'tabular-nums' }}>{r.when}</td>
                <td>{r.who}</td>
                <td>{r.action}</td>
                <td>{r.organization}</td>
                <td style={{ whiteSpace: 'normal' }}>{r.what}</td>
                <td style={{ color: r.result === 'ok' ? 'var(--good)' : 'var(--conflict)' }}>{r.result}</td>
              </>
            )}
            footer={(l) => `${l.filter((r) => r.result === 'refused').length} refused`}
          />
        ) : null}
      </div>
    </>
  );
}
