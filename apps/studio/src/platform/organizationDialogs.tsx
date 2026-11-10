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
import { t, useT } from '../i18n/i18n';
import { store } from '../store/store';
import { PlatformDialog } from './PlatformDialog';

/** The `Companies` select: `Several companies` first, as the default of a new organization. */
function CompaniesSelect({ id, value, onChange }: { id: string; value: CompanyMode; onChange: (mode: CompanyMode) => void }) {
  const t = useT();
  return (
    <>
      <label htmlFor={id}>{t('platform.organization.companies')}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value as CompanyMode)}>
        <option value="multiple">{t('platform.organizations.severalCompanies')}</option>
        <option value="single">{t('platform.organizations.oneCompany')}</option>
      </select>
    </>
  );
}

export function createOrganizationDialog(done: () => void): void {
  store.openDialog({ render: (close) => <CreateOrganization close={close} done={done} /> });
}

function CreateOrganization({ close, done }: { close: () => void; done: () => void }) {
  const t = useT();
  const [name, setName] = useState('');
  const [mode, setMode] = useState<CompanyMode>('multiple');
  return (
    <PlatformDialog
      title={t('platform.organization.createTitle')}
      close={close}
      label={t('platform.organization.create')}
      onSave={() =>
        api.createOrganization({ name: name.trim(), companyMode: mode }).then((org) => {
          store.toast2(t('platform.organization.created'), org.name);
          done();
        })
      }
    >
      <label htmlFor="orgName">{t('platform.organization.name')}</label>
      <input id="orgName" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
      <CompaniesSelect id="orgMode" value={mode} onChange={setMode} />
    </PlatformDialog>
  );
}

export function renameOrganizationDialog(org: Organization, done: () => void): void {
  store.openDialog({ render: (close) => <RenameOrganization org={org} close={close} done={done} /> });
}

function RenameOrganization({ org, close, done }: { org: Organization; close: () => void; done: () => void }) {
  const t = useT();
  const [name, setName] = useState(org.name);
  return (
    <PlatformDialog
      title={t('platform.organization.renameTitle', { name: org.name })}
      close={close}
      label={t('common.rename')}
      onSave={() =>
        api.updateOrganization(org.id, { name: name.trim() }).then((next) => {
          store.toast2(t('platform.organization.renamed'), next.name);
          done();
        })
      }
    >
      <label htmlFor="orgRename">{t('platform.organization.name')}</label>
      <input id="orgRename" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
    </PlatformDialog>
  );
}

export function editOrganizationDialog(org: Organization, done: () => void): void {
  store.openDialog({ render: (close) => <EditOrganization org={org} close={close} done={done} /> });
}

function EditOrganization({ org, close, done }: { org: Organization; close: () => void; done: () => void }) {
  const t = useT();
  const [mode, setMode] = useState<CompanyMode>(org.companyMode);
  return (
    <PlatformDialog
      title={t('platform.organization.editTitle', { name: org.name })}
      close={close}
      label={t('common.save')}
      onSave={() => {
        if (mode === org.companyMode) return Promise.resolve();
        return api.updateOrganization(org.id, { companyMode: mode }).then(() => {
          store.toast2(t('platform.organization.saved'), org.name);
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
    t('platform.organization.disableTitle', { name: org.name }),
    t('platform.organization.disableBody', { name: org.name }),
    t('common.disable'),
    () =>
      attempt(() => api.disableOrganization(org.id)).then((res) => {
        if (!res) return;
        store.toast2(t('platform.organization.disabled'), org.name);
        done();
      }),
    true,
  );
}

export function enableOrganization(org: Organization, done: () => void): Promise<void> {
  return attempt(() => api.enableOrganization(org.id)).then((res) => {
    if (!res) return;
    store.toast2(t('platform.organization.enabled'), org.name);
    done();
  });
}

/** `Enter <organization>?` in the reference's `confirmDialog`; on yes the session moves inside it. */
export function enterOrganizationDialog(org: Organization): void {
  confirmDialog(
    t('platform.organization.enterTitle', { name: org.name }),
    t('platform.organization.enterBody', { name: org.name }),
    t('platform.organization.enter'),
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
  const t = useT();
  const [reason, setReason] = useState('');
  return (
    <PlatformDialog
      title={t('platform.organization.openTitle', { name: org.name })}
      sub={t('platform.organization.openSub')}
      close={close}
      label={t('common.open')}
      onSave={() => api.startSupportSession(org.id, reason.trim()).then((session) => auth.replaceSession(session))}
    >
      <label htmlFor="supportReason">{t('platform.organization.reason')}</label>
      <input id="supportReason" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
    </PlatformDialog>
  );
}
