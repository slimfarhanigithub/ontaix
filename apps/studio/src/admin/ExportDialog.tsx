/**
 * The Export dialog of the admin portal's Companies page (decision rows 141 and 142, ADR 0016),
 * an owner addition absent from the reference, in the reference's own `dialog()` markup: a format
 * and a scope, then the file the API writes from the approved model, saved by the browser.
 */
import { useState } from 'react';

import { api, type ExportFormat, type ExportRequest } from '../api/client';
import type { Company } from '../canvas/types';
import { store } from '../store/store';
import { useStore } from '../shell/dom';
import { attempt } from './adminData';

type ExportScope = ExportRequest['scope'];

export const EXPORT_FORMATS: [ExportFormat, string][] = [
  ['owl', 'OWL 2 · RDF/XML (.owl)'],
  ['owx', 'OWL 2 · OWL/XML (.owx)'],
  ['turtle', 'OWL 2 · Turtle (.ttl)'],
  ['jsonld', 'OWL 2 · JSON-LD (.jsonld)'],
  ['skos', 'SKOS · Turtle (.skos.ttl)'],
  ['docx', 'Word document (.docx)'],
];

export const EXPORT_SCOPES: [ExportScope, string][] = [
  ['all', 'Everything I can read'],
  ['company', 'One company'],
  ['domain', 'One domain product'],
];

/** Domain products of the company that hold a concept, in ring order. */
function domainsOf(c: Company | undefined) {
  if (!c) return [];
  return c.domains.filter((d) => d.sid && store.s.nodes.some((n) => n.domain === d && !n.dying));
}

function ExportForm() {
  const st = useStore();
  const companies = st.s.companies.filter((c) => c.sid);
  const active = st.s.activeCompany && st.s.activeCompany.sid ? st.s.activeCompany : companies[0];
  const [scope, setScope] = useState<ExportScope>('all');
  const [companySid, setCompanySid] = useState(active?.sid || '');
  const company = companies.find((c) => c.sid === companySid);
  return (
    <div className="form">
      <label>Format</label>
      <select id="exFormat" defaultValue="owl">
        {EXPORT_FORMATS.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <label>Scope</label>
      <select id="exScope" value={scope} onChange={(e) => setScope(e.target.value as ExportScope)}>
        {EXPORT_SCOPES.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      {scope !== 'all' ? (
        <>
          <label>Company</label>
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
          <label>Domain product</label>
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
    title: 'Export the ontology',
    sub: 'the approved model as OWL, SKOS or a Word document',
    body: <ExportForm />,
    buttons: [
      {
        label: 'Export',
        cls: 'primary',
        onClick: (bk) => {
          const request = exportRequest(bk);
          if (!request) return false;
          return attempt(() => api.exportOntology(request)).then((file) => {
            if (!file) return false;
            save(file.blob, file.fileName);
            store.toast2('Exported', file.fileName);
          });
        },
      },
    ],
  });
}
