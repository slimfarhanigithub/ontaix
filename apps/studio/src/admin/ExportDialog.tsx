/**
 * The Export dialog of the admin portal's Companies page (ADR 0016),
 * an owner addition absent from the reference, in the reference's own `dialog()` markup: a format
 * and a scope, then the file the API writes from the approved model, saved by the browser.
 */
import { useState } from 'react';

import { api, type ExportFormat, type ExportRequest } from '../api/client';
import type { Company } from '../canvas/types';
import { t, useT, type MessageKey } from '../i18n/i18n';
import { store } from '../store/store';
import { useStore } from '../shell/dom';
import { attempt } from './adminData';

type ExportScope = ExportRequest['scope'];

/** The formats in the order the select lists them, each with the key of its label. */
export const EXPORT_FORMATS: [ExportFormat, MessageKey][] = [
  ['owl', 'admin.export.format.owl'],
  ['owx', 'admin.export.format.owx'],
  ['turtle', 'admin.export.format.turtle'],
  ['jsonld', 'admin.export.format.jsonld'],
  ['skos', 'admin.export.format.skos'],
  ['docx', 'admin.export.format.docx'],
];

export const EXPORT_SCOPES: [ExportScope, MessageKey][] = [
  ['all', 'admin.export.scope.all'],
  ['company', 'admin.export.scope.company'],
  ['domain', 'admin.export.scope.domain'],
];

/** Domain products of the company that hold a concept, in ring order. */
function domainsOf(c: Company | undefined) {
  if (!c) return [];
  return c.domains.filter((d) => d.sid && store.s.nodes.some((n) => n.domain === d && !n.dying));
}

function ExportForm() {
  const st = useStore();
  const t = useT();
  const companies = st.s.companies.filter((c) => c.sid);
  const active = st.s.activeCompany && st.s.activeCompany.sid ? st.s.activeCompany : companies[0];
  const [scope, setScope] = useState<ExportScope>('all');
  const [companySid, setCompanySid] = useState(active?.sid || '');
  const company = companies.find((c) => c.sid === companySid);
  return (
    <div className="form">
      <label>{t('admin.export.format')}</label>
      <select id="exFormat" defaultValue="owl">
        {EXPORT_FORMATS.map(([value, label]) => (
          <option key={value} value={value}>
            {t(label)}
          </option>
        ))}
      </select>
      <label>{t('admin.export.scope')}</label>
      <select id="exScope" value={scope} onChange={(e) => setScope(e.target.value as ExportScope)}>
        {EXPORT_SCOPES.map(([value, label]) => (
          <option key={value} value={value}>
            {t(label)}
          </option>
        ))}
      </select>
      {scope !== 'all' ? (
        <>
          <label>{t('admin.col.company')}</label>
          <select id="exCompany" value={companySid} onChange={(e) => setCompanySid(e.target.value)}>
            {companies.map((c) => (
              <option key={c.sid} value={c.sid || ''}>
                {c.name}
              </option>
            ))}
          </select>
        </>
      ) : null}
      {scope === 'domain' ? (
        <>
          <label>{t('admin.col.domain')}</label>
          <select id="exDomain" key={companySid}>
            {domainsOf(company).map((d) => (
              <option key={d.sid} value={d.sid || ''}>
                {d.name}
              </option>
            ))}
          </select>
        </>
      ) : null}
    </div>
  );
}

/** The request the form describes, or null when a company or domain product is missing. */
export function exportRequest(root: HTMLElement): ExportRequest | null {
  const format = (root.querySelector<HTMLSelectElement>('#exFormat')?.value || 'owl') as ExportFormat;
  const scope = (root.querySelector<HTMLSelectElement>('#exScope')?.value || 'all') as ExportScope;
  if (scope === 'all') return { scope, format };
  if (scope === 'company') {
    const companyId = root.querySelector<HTMLSelectElement>('#exCompany')?.value;
    return companyId ? { scope, companyId, format } : null;
  }
  const domainProductId = root.querySelector<HTMLSelectElement>('#exDomain')?.value;
  return domainProductId ? { scope, domainProductId, format } : null;
}

/** Hands the file to the browser as a download. */
function save(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function openExport(): void {
  store.openDialog({
    title: t('admin.export.title'),
    sub: t('admin.export.sub'),
    body: <ExportForm />,
    buttons: [
      {
        label: t('admin.export.action'),
        cls: 'primary',
        onClick: (bk) => {
          const request = exportRequest(bk);
          if (!request) return false;
          return attempt(() => api.exportOntology(request)).then((file) => {
            if (!file) return false;
            save(file.blob, file.fileName);
            store.toast2(t('admin.export.exportedLead'), file.fileName);
          });
        },
      },
    ],
  });
}
