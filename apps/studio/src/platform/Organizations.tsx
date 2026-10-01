/**
 * The platform portal's Organizations page: the list of organizations in the reference's list
 * pattern, `+ Create an organization`, and the row actions Users, Open, Rename and Disable or
 * Enable. Clicking a row opens `Edit <name>`, where the company mode is changed.
 */
import { useCallback, useEffect, useState } from 'react';

import { failed, fetchAll } from '../admin/adminData';
import { List, type Column } from '../admin/List';
import { api } from '../api/client';
import type { Organization } from '../api/types';
import {
  createOrganizationDialog,
  disableOrganizationDialog,
  editOrganizationDialog,
  enableOrganization,
  openSupportDialog,
  renameOrganizationDialog,
} from './organizationDialogs';
import { usersDialog } from './OrganizationUsers';

const ACT = (w: number) => ({ width: `${w}px`, textAlign: 'center' as const });

export const companiesText = (org: Pick<Organization, 'companyMode'>): string => (org.companyMode === 'single' ? 'One company' : 'Several companies');
export const statusText = (org: Pick<Organization, 'status'>): string => (org.status === 'disabled' ? 'Disabled' : 'Active');

/** `dd Mon yyyy` in en-GB, the way the reference dates its lists. */
export const dateText = (iso: string): string => new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

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
        failed(err, 'Unavailable');
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
    { label: 'Name', key: 'name' },
    { label: 'Companies', key: 'companies' },
    { label: 'Users', key: 'users', num: true },
    { label: 'Status', key: 'status' },
    { label: 'Created', key: 'createdAt' },
    // Four buttons (48, 44, 56 and 56 wide plus 22 of padding and border each), three 6px gaps and
    // the cell padding: 330px, which leaves the five text columns their room at 1440 wide.
    { label: '', w: '330px' },
  ];
  return (
    <>
      <h2>Organizations</h2>
      <p className="lead">
        Each organization is its own instance: its users see only its data. Only a super admin creates organizations and their accounts.
      </p>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
        <button className="btn primary" data-act="newOrg" onClick={() => createOrganizationDialog(refresh)}>
          + Create an organization
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
                  <button data-fn="users" style={ACT(48)} onClick={() => usersDialog(r.org, refresh)}>
                    Users
                  </button>
                  <button data-fn="open" style={ACT(44)} onClick={() => openSupportDialog(r.org)}>
                    Open
                  </button>
                  <button data-fn="rename" style={ACT(56)} onClick={() => renameOrganizationDialog(r.org, refresh)}>
                    Rename
                  </button>
                  {r.org.status === 'disabled' ? (
                    <button data-fn="enable" style={ACT(56)} onClick={() => void enableOrganization(r.org, refresh)}>
                      Enable
                    </button>
                  ) : (
                    <button className="danger" data-fn="disable" style={ACT(56)} onClick={() => disableOrganizationDialog(r.org, refresh)}>
                      Disable
                    </button>
                  )}
                </td>
              </>
            )}
            footer={(l) => `${l.reduce((a, r) => a + r.users, 0)} users`}
          />
        ) : null}
      </div>
    </>
  );
}
