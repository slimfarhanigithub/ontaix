/**
 * The dialogs of the Organizations page: create, rename, edit (the company mode), the typed
 * confirmation before disabling, the reason asked before a read-only support session opens, and
 * the confirmation before the super admin enters an organization to act inside it.
 * Every text is ADR 0017's; every refusal shows the Problem's `detail` in the dialog's `.msg`.
 */
import { useState } from 'react';

import { confirmDialog } from '../admin/actions';
import { attempt } from '../admin/adminData';
import { api } from '../api/client';
import type { CompanyMode, Organization } from '../api/types';
import { auth } from '../auth/authStore';
import { store } from '../store/store';
import { PlatformDialog } from './PlatformDialog';

/** The `Companies` select: `Several companies` first, as the default of a new organization. */
function CompaniesSelect({ id, value, onChange }: { id: string; value: CompanyMode; onChange: (mode: CompanyMode) => void }) {
  return (
    <>
      <label htmlFor={id}>Companies</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value as CompanyMode)}>
        <option value="multiple">Several companies</option>
        <option value="single">One company</option>
      </select>
    </>
  );
}

export function createOrganizationDialog(done: () => void): void {
  store.openDialog({ render: (close) => <CreateOrganization close={close} done={done} /> });
}

function CreateOrganization({ close, done }: { close: () => void; done: () => void }) {
  const [name, setName] = useState('');
  const [mode, setMode] = useState<CompanyMode>('multiple');
  return (
    <PlatformDialog
      title="Create an organization"
      close={close}
      label="Create"
      onSave={() =>
        api.createOrganization({ name: name.trim(), companyMode: mode }).then((org) => {
          store.toast2('Created', org.name);
          done();
        })
      }
    >
      <label htmlFor="orgName">Name</label>
      <input id="orgName" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
      <CompaniesSelect id="orgMode" value={mode} onChange={setMode} />
    </PlatformDialog>
  );
}

export function renameOrganizationDialog(org: Organization, done: () => void): void {
  store.openDialog({ render: (close) => <RenameOrganization org={org} close={close} done={done} /> });
}

function RenameOrganization({ org, close, done }: { org: Organization; close: () => void; done: () => void }) {
  const [name, setName] = useState(org.name);
  return (
    <PlatformDialog
      title={`Rename ${org.name}`}
      close={close}
      label="Rename"
      onSave={() =>
        api.updateOrganization(org.id, { name: name.trim() }).then((next) => {
          store.toast2('Renamed', next.name);
          done();
        })
      }
    >
      <label htmlFor="orgRename">Name</label>
      <input id="orgRename" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
    </PlatformDialog>
  );
}

export function editOrganizationDialog(org: Organization, done: () => void): void {
  store.openDialog({ render: (close) => <EditOrganization org={org} close={close} done={done} /> });
}

function EditOrganization({ org, close, done }: { org: Organization; close: () => void; done: () => void }) {
  const [mode, setMode] = useState<CompanyMode>(org.companyMode);
  return (
    <PlatformDialog
      title={`Edit ${org.name}`}
      close={close}
      label="Save"
      onSave={() => {
        if (mode === org.companyMode) return Promise.resolve();
        return api.updateOrganization(org.id, { companyMode: mode }).then(() => {
          store.toast2('Saved', org.name);
          done();
        });
      }}
    >
      <CompaniesSelect id="orgEditMode" value={mode} onChange={setMode} />
    </PlatformDialog>
  );
}

/** `Disable <organization>?` in the reference's `confirmDialog` with a `danger` button. */
export function disableOrganizationDialog(org: Organization, done: () => void): void {
  confirmDialog(
    `Disable ${org.name}?`,
    `Every user of ${org.name} is signed out and can no longer sign in. Its data is kept.`,
    'Disable',
    () =>
      attempt(() => api.disableOrganization(org.id)).then((res) => {
        if (!res) return;
        store.toast2('Disabled', org.name);
        done();
      }),
    true,
  );
}

export function enableOrganization(org: Organization, done: () => void): Promise<void> {
  return attempt(() => api.enableOrganization(org.id)).then((res) => {
    if (!res) return;
    store.toast2('Enabled', org.name);
    done();
  });
}

/** `Enter <organization>?` in the reference's `confirmDialog`; on yes the session moves inside it. */
export function enterOrganizationDialog(org: Organization): void {
  confirmDialog(
    `Enter ${org.name}?`,
    `You act inside ${org.name} with every role, as platform super admin. Everything you do there is recorded in its audit log.`,
    'Enter',
    () =>
      attempt(() => api.enterOrganization(org.id)).then((session) => {
        if (session) auth.replaceSession(session);
      }),
  );
}

export function openSupportDialog(org: Organization): void {
  store.openDialog({ render: (close) => <OpenSupport org={org} close={close} /> });
}

function OpenSupport({ org, close }: { org: Organization; close: () => void }) {
  const [reason, setReason] = useState('');
  return (
    <PlatformDialog
      title={`Open ${org.name}`}
      sub="A read-only support session for 60 minutes, recorded in its audit log"
      close={close}
      label="Open"
      onSave={() => api.startSupportSession(org.id, reason.trim()).then((session) => auth.replaceSession(session))}
    >
      <label htmlFor="supportReason">Reason</label>
      <input id="supportReason" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
    </PlatformDialog>
  );
}
