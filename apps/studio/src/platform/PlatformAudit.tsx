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
import { formatDate, formatTime, t, useT } from '../i18n/i18n';

interface AuditRow extends Record<string, unknown> {
  id: number;
  at: string;
  when: string;
  who: string;
  action: string;
  organization: string;
  what: string;
  ok: boolean;
  /** `ok` or `refused` in the portal language; the filter pills and the search read it. */
  result: string;
}

/** `dd Mon yyyy, hh:mm:ss` in the portal language. */
export const whenText = (iso: string): string => `${formatDate(iso)}, ${formatTime(iso)}`;

export function auditRow(e: PlatformAuditEntry): AuditRow {
  return {
    id: e.id,
    at: e.at,
    when: whenText(e.at),
    who: e.actor?.email || '—',
    action: e.action,
    organization: e.organization?.name || '—',
    what: e.what,
    ok: e.ok,
    result: e.ok ? t('platform.audit.ok') : t('platform.audit.refused'),
  };
}

export function PlatformAudit() {
  const t = useT();
  const [entries, setEntries] = useState<PlatformAuditEntry[] | null>(null);
  useEffect(() => {
    let live = true;
    api.listPlatformAudit({ page: 1, pageSize: AUDIT_SHOWN }).then(
      (page) => {
        if (live) setEntries(page.items);
      },
      (err: unknown) => {
        failed(err, t('common.lead.unavailable'));
        if (live) setEntries([]);
      },
    );
    return () => {
      live = false;
    };
  }, []);
  const rows = (entries || []).map(auditRow);
  const columns: Column[] = [
    { label: t('platform.audit.column.when'), key: 'at' },
    { label: t('platform.audit.column.who'), key: 'who' },
    { label: t('platform.audit.column.action'), key: 'action' },
    { label: t('platform.audit.column.organization'), key: 'organization' },
    { label: t('platform.audit.column.what'), key: 'what' },
    { label: t('platform.audit.column.result'), key: 'result' },
  ];
  return (
    <>
      <h2>{t('platform.audit.heading')}</h2>
      <p className="lead">{t('platform.audit.lead')}</p>
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
                <td style={{ color: r.ok ? 'var(--good)' : 'var(--conflict)' }}>{r.result}</td>
              </>
            )}
            footer={(l) => t('platform.audit.footer', { n: l.filter((r) => !r.ok).length })}
          />
        ) : null}
      </div>
    </>
  );
}
