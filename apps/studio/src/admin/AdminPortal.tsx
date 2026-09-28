/**
 * The admin portal's navigation and the page it shows (`renderAdmin`, reference line 957): four
 * groups, fifteen pages in the contract's order, live counts beside the lists.
 */
import { useEffect, type ReactNode } from 'react';

import { useStore } from '../shell/dom';
import { directory, loadDirectory } from './adminData';
import { Connectors, DataSources } from './pages/DataPages';
import { AuditLog, CostManagement, Groups, Roles, Users } from './pages/GovernancePages';
import { Bindings, Companies, DomainProducts, Entities, Relationships } from './pages/ModelPages';
import { Appearance, Overview, TenantSettings } from './pages/PortalPages';

type Store = ReturnType<typeof useStore>;

type NavItem = ['grp', string] | [string, string, ((st: Store) => number)?];

const NAV: NavItem[] = [
  ['grp', 'Portal'],
  ['overview', 'Overview'],
  ['settings', 'Tenant settings'],
  ['appearance', 'Appearance'],
  ['grp', 'Data'],
  ['sources', 'Data sources', (st) => st.s.nodes.filter((n) => n.kind === 'source').length],
  ['connectors', 'Connectors'],
  ['grp', 'Model'],
  ['entities', 'Entities', (st) => st.s.nodes.filter((n) => n.kind === 'concept' && !n.dying).length],
  ['relations', 'Relationships', (st) => st.s.links.filter((l) => l.kind !== 'bind' && !l.dying).length],
  ['bindings', 'Bindings', (st) => st.s.nodes.filter((n) => n.bound).length],
  ['companies', 'Companies', (st) => st.s.companies.length],
  ['domains', 'Domain products', (st) => st.s.DOMAINS.filter((d) => st.s.nodes.some((n) => n.domain === d)).length],
  ['grp', 'Governance'],
  ['groups', 'Groups', () => directory.groups.length],
  ['users', 'Users', () => directory.users.length],
  ['roles', 'Roles'],
  ['audit', 'Audit log', () => directory.auditTotal],
  ['agents', 'Cost management'],
];

const PAGES: Record<string, () => ReactNode> = {
  overview: () => <Overview />,
  settings: () => <TenantSettings />,
  appearance: () => <Appearance />,
  sources: () => <DataSources />,
  connectors: () => <Connectors />,
  entities: () => <Entities />,
  relations: () => <Relationships />,
  bindings: () => <Bindings />,
  companies: () => <Companies />,
  domains: () => <DomainProducts />,
  groups: () => <Groups />,
  users: () => <Users />,
  roles: () => <Roles />,
  audit: () => <AuditLog />,
  agents: () => <CostManagement />,
};

export function AdminNav() {
  const st = useStore();
  const page = st.ui.adminPage;
  return (
    <>
      {NAV.map((p, i) =>
        p[0] === 'grp' ? (
          <div className="grp" key={i}>
            {p[1]}
          </div>
        ) : (
          <button key={p[0]} data-page={p[0]} className={page === p[0] ? 'on' : ''} onClick={() => st.setAdminPage(p[0])}>
            {p[1]}
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
    if (adminOpen) void loadDirectory(adminRev);
  }, [adminOpen, adminRev]);
  const render = PAGES[adminPage] || PAGES.sources;
  return <>{render()}</>;
}
