/**
 * The platform portal's Organizations page: the list of organizations in the reference's list
 * pattern, `+ Create an organization`, and the row actions Users, Enter, Open, Rename and
 * Disable or Enable. Clicking a row opens `Edit <name>`, where the company mode is changed.
 */
import { useCallback, useEffect, useState } from 'react';

import { failed, fetchAll } from '../admin/adminData';
import { List, type Column } from '../admin/List';
import { api } from '../api/client';
import type { Organization } from '../api/types';
import { formatDate, t, useT } from '../i18n/i18n';
import {
  createOrganizationDialog,
  disableOrganizationDialog,
  editOrganizationDialog,
  enableOrganization,
  enterOrganizationDialog,
  openSupportDialog,
  renameOrganizationDialog,
} from './organizationDialogs';
import { usersDialog } from './OrganizationUsers';
import { RowActions } from '../admin/RowActions';

const ACT = (w: number) => ({ width: `${w}px`, textAlign: 'center' as const });

export const companiesText = (org: Pick<Organization, 'companyMode'>): string =>
  org.companyMode === 'single' ? t('platform.organizations.oneCompany') : t('platform.organizations.severalCompanies');
export const statusText = (org: Pick<Organization, 'status'>): string =>
  org.status === 'disabled' ? t('platform.organizations.disabled') : t('platform.organizations.active');

/** `dd Mon yyyy` in the portal language, the way the reference dates its lists. */
export const dateText = (iso: string): string => formatDate(iso);

interface OrgRow extends Record<string, unknown> {
  id: string;
  org: Organization;
  name: string;
  companies: string;
  users: number;
  status: string;
  created: string;
}

/** Every organization, reloaded whenever `rev` changes; a refusal leaves the list empty with a toast. */
function useOrganizations(rev: number): Organization[] | null {
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  useEffect(() => {
    let live = true;
    fetchAll((p) => api.listOrganizations(p)).then(
      (items) => {
        if (live) setOrgs(items);
      },
      (err: unknown) => {
        failed(err, t('common.lead.unavailable'));
        if (live) setOrgs([]);
      },
    );
    return () => {
      live = false;
    };
  }, [rev]);
  return orgs;
}

export function Organizations() {
  const t = useT();
  const [rev, setRev] = useState(0);
  const refresh = useCallback(() => setRev((r) => r + 1), []);
  const orgs = useOrganizations(rev);
  const rows: OrgRow[] = (orgs || []).map((org) => ({
    id: org.id,
    org,
    name: org.name,
    companies: companiesText(org),
    users: org.users,
    status: statusText(org),
    created: dateText(org.createdAt),
    createdAt: org.createdAt,
  }));
  const columns: Column[] = [
    { label: t('platform.organizations.column.name'), key: 'name' },
    { label: t('platform.organizations.column.companies'), key: 'companies' },
    { label: t('platform.organizations.column.users'), key: 'users', num: true },
    { label: t('platform.organizations.column.status'), key: 'status' },
    { label: t('platform.organizations.column.created'), key: 'createdAt' },
    // Five buttons (38, 36, 36, 52 and 50 wide plus 16 of padding and border each, the padding
    // narrowed for this list), four 6px gaps and the cell padding: 336px, which leaves the five
    // text columns their room at 1440 wide.
    { label: '', w: '336px' },
  ];
  return (
    <>
      <h2>{t('platform.organizations.heading')}</h2>
      <p className="lead">{t('platform.organizations.lead')}</p>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
        <button className="btn primary" data-act="newOrg" onClick={() => createOrganizationDialog(refresh)}>
          {t('platform.organizations.create')}
        </button>
      </div>
      <div className="lst-host" id="lstOrganizations" style={{ height: 'calc(100% - 120px)' }}>
        {orgs ? (
          <List
            key={rev}
            columns={columns}
            rows={rows}
            rowKey={(r) => r.id}
            searchKeys={['name', 'companies', 'status']}
            filterKey="status"
            pageSize={40}
            onRowClick={(r) => editOrganizationDialog(r.org, refresh)}
            renderRow={(r) => (
              <>
                <td>
                  <b>{r.name}</b>
                </td>
                <td>{r.companies}</td>
                <td className="num">{r.users}</td>
                <td>
                  <span className={`st${r.org.status === 'disabled' ? ' off' : ''}`}>
                    <i></i>
                    {r.status}
                  </span>
                </td>
                <td style={{ color: 'var(--ink-2)' }}>{r.created}</td>
                <td className="act">
                  <RowActions
                    id={`org-${r.org.id}`}
                    primary={
                      <button data-fn="enter" style={ACT(50)} onClick={() => enterOrganizationDialog(r.org)}>
                        {t('platform.organizations.enter')}
                      </button>
                    }
                    items={[
                      { label: t('platform.organizations.users'), icon: 'people', group: 1, attrs: { 'data-fn': 'users' }, act: () => usersDialog(r.org, refresh) },
                      { label: t('common.open'), icon: 'open', group: 1, attrs: { 'data-fn': 'open' }, act: () => openSupportDialog(r.org) },
                      { label: t('common.rename'), icon: 'rename', group: 1, attrs: { 'data-fn': 'rename' }, act: () => renameOrganizationDialog(r.org, refresh) },
                      r.org.status === 'disabled'
                        ? { label: t('common.enable'), icon: 'power', group: 2, attrs: { 'data-fn': 'enable' }, act: () => void enableOrganization(r.org, refresh) }
                        : { label: t('common.disable'), icon: 'power', group: 2, danger: true, attrs: { 'data-fn': 'disable' }, act: () => disableOrganizationDialog(r.org, refresh) },
                    ]}
                  />
                </td>
              </>
            )}
            footer={(l) => t('platform.organizations.footer', { n: l.reduce((a, r) => a + r.users, 0) })}
          />
        ) : null}
      </div>
    </>
  );
}
