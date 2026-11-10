/**
 * The admin portal's navigation and the page it shows (`renderAdmin`, reference line 957): three
 * groups, nine pages in the contract's order, live counts beside the lists.
 */
import { useEffect, type ReactNode } from 'react';

import { t, useT, type MessageKey } from '../i18n/i18n';
import { useStore } from '../shell/dom';
import { directory, invalidateDirectory, loadDirectory } from './adminData';
import { AuditLog, CostManagement } from './pages/GovernancePages';
import { Companies, DomainProducts, Entities, Relationships } from './pages/ModelPages';
import { Appearance, Overview, TenantSettings } from './pages/PortalPages';

type Store = ReturnType<typeof useStore>;

/** A group heading or a page: its id, the key of its label and, for a list, its live count. */
type NavItem = ['grp', MessageKey] | [string, MessageKey, ((st: Store) => number)?];

const NAV: NavItem[] = [
  ['grp', 'admin.nav.portal'],
  ['overview', 'admin.nav.overview'],
  ['settings', 'admin.nav.settings'],
  ['appearance', 'admin.nav.appearance'],
  ['grp', 'admin.nav.model'],
  ['entities', 'admin.nav.entities', (st) => st.s.nodes.filter((n) => n.kind === 'concept' && !n.dying).length],
  ['relations', 'admin.nav.relations', (st) => st.s.links.filter((l) => l.kind !== 'bind' && !l.dying).length],
  ['companies', 'admin.nav.companies', (st) => st.s.companies.length],
  ['domains', 'admin.nav.domains', (st) => st.s.DOMAINS.filter((d) => st.s.nodes.some((n) => n.domain === d)).length],
  ['grp', 'admin.nav.governance'],
  ['audit', 'admin.nav.audit', () => directory.auditTotal],
  ['agents', 'admin.nav.cost'],
];

const PAGES: Record<string, () => ReactNode> = {
  overview: () => <Overview />,
  settings: () => <TenantSettings />,
  appearance: () => <Appearance />,
  entities: () => <Entities />,
  relations: () => <Relationships />,
  companies: () => <Companies />,
  domains: () => <DomainProducts />,
  audit: () => <AuditLog />,
  agents: () => <CostManagement />,
};

export function AdminNav() {
  const st = useStore();
  useT();
  const page = st.ui.adminPage;
  return (
    <>
      {NAV.map((p, i) =>
        p[0] === 'grp' ? (
          <div className="grp" key={i}>
            {t(p[1])}
          </div>
        ) : (
          <button key={p[0]} data-page={p[0]} className={page === p[0] ? 'on' : ''} onClick={() => st.setAdminPage(p[0])}>
            {t(p[1])}
            {p[2] ? <span>{p[2](st)}</span> : null}
          </button>
        ),
      )}
    </>
  );
}

export function AdminMain() {
  const st = useStore();
  const { adminOpen, adminRev, adminPage } = st.ui;
  useEffect(() => {
    if (adminOpen) invalidateDirectory();
  }, [adminOpen]);
  useEffect(() => {
    if (adminOpen) void loadDirectory();
  }, [adminOpen, adminRev]);
  const render = PAGES[adminPage] || PAGES.overview;
  return <>{render()}</>;
}
