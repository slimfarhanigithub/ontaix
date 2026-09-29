import { act, render } from '@testing-library/react';

import { addCompany, addLink, addNode, domainOf } from '../canvas/state';
import type { Company, Node } from '../canvas/types';
import { Dialog } from '../shell/Dialog';
import { Drawer } from '../shell/Drawer';
import { store } from '../store/store';
import { deleteNodeDialog } from './actions';
import { canDeleteFromDrawer, conceptDeletion, deletionText } from './conceptDeletion';

const PAYLOAD = '<img src=x onerror=alert(1)>';

function reset(): Company {
  const s = store.s;
  s.nodes.length = 0;
  s.links.length = 0;
  s.companies.length = 0;
  s.DOMAINS = [];
  return addCompany(s, 'Northwind Industries', '');
}

const rootOf = (c: Company): Node => {
  if (!c.root) throw new Error('company without a root');
  return c.root;
};

function cell(c: Company, label: string, parent: Node | null, extra: Partial<Node> = {}): Node {
  return addNode(store.s, { label, kind: 'concept', company: c, domain: domainOf(store.s, 'production', c), parent: parent ?? undefined, sid: `sid-${label}`, ...extra });
}

/** Services with four descendants (Apps and Data one and two generations down) and five relations touching them. */
function servicesModel() {
  const s = store.s;
  const c = reset();
  const services = cell(c, 'Services', c.root);
  const offerings = cell(c, 'Offerings', services);
  const apps = cell(c, 'Apps', services);
  const data = cell(c, 'Data', apps);
  const ai = cell(c, 'AI', services);
  const other = cell(c, 'Plant', c.root);
  addLink(s, services, offerings, 'isa');
  addLink(s, services, apps, 'rel', 230, 'runs');
  addLink(s, apps, data, 'rel', 230, 'uses');
  addLink(s, ai, other, 'rel', 230, 'serves');
  addLink(s, other, services, 'rel', 230, 'buys');
  addLink(s, other, rootOf(c), 'rel', 230, 'belongs to');
  addLink(s, services, other, 'rel', 230, 'gone').dying = { start: 0 };
  addLink(s, other, data, 'bind');
  return { c, services, offerings, apps, data, ai, other };
}

describe('concept deletion', () => {
  afterEach(() => {
    store.ui.dialogs = [];
    store.ui.drawerNode = null;
  });

  it('counts descendants through the parent chain and each touching relation once', () => {
    const { services, data, other } = servicesModel();
    const d = conceptDeletion(store.s, services);
    expect(d.descendants.map((x) => x.label).sort()).toEqual(['AI', 'Apps', 'Data', 'Offerings']);
    expect(d.relations).toBe(5);
    expect(conceptDeletion(store.s, data)).toEqual({ descendants: [], relations: 1 });
    expect(conceptDeletion(store.s, other).relations).toBe(3);
  });

  it('leaves dying descendants out', () => {
    const { services, ai } = servicesModel();
    ai.dying = { start: 0 } as Node['dying'];
    expect(conceptDeletion(store.s, services).descendants.map((x) => x.label)).not.toContain('AI');
  });

  it('writes the confirmation for zero, one, many and more than six descendants', () => {
    expect(deletionText([], 0)).toBe('Its 0 relations go with it. This proposes a change for approval.');
    expect(deletionText([], 1)).toBe('Its 1 relation goes with it. This proposes a change for approval.');
    expect(deletionText([], 3)).toBe('Its 3 relations go with it. This proposes a change for approval.');
    expect(deletionText(['Apps'], 1)).toBe('Its 1 descendant (Apps) and 1 relation go with it. This proposes a change for approval.');
    expect(deletionText(['Offerings', 'Apps', 'Data', 'AI'], 5)).toBe(
      'Its 4 descendants (Offerings, Apps, Data, AI) and 5 relations go with it. This proposes a change for approval.',
    );
    expect(deletionText(['A', 'B', 'C', 'D', 'E', 'F'], 2)).toBe('Its 6 descendants (A, B, C, D, E, F) and 2 relations go with it. This proposes a change for approval.');
    expect(deletionText(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I'], 12)).toBe(
      'Its 9 descendants (A, B, C, D, E, F and 3 more) and 12 relations go with it. This proposes a change for approval.',
    );
  });

  it('names what goes in the dialog, with names rendered as text', () => {
    const { services } = servicesModel();
    const { container } = render(<Dialog />);
    act(() => deleteNodeDialog(services));
    const dlg = container.querySelector('.dlg');
    expect(dlg?.querySelector('.dh b')?.textContent).toBe('Delete Services?');
    expect(dlg?.querySelector('.db')?.textContent).toMatch(/^Its 4 descendants \((Offerings|Apps|Data|AI)(, (Offerings|Apps|Data|AI)){3}\) and 5 relations go with it\./);
    const made: Node[] = [];
    act(() => {
      store.ui.dialogs = [];
      const c = reset();
      made.push(cell(c, 'Root child', c.root));
      cell(c, PAYLOAD, made[0]);
      store.bump();
    });
    act(() => deleteNodeDialog(made[0]));
    expect(container.querySelector('.dlg img')).toBeNull();
    expect(container.querySelector('.dlg .db')?.textContent).toContain(`(${PAYLOAD})`);
  });

  it('offers Delete in the drawer only for approved concepts, never for the root, sources or pending cells', () => {
    const { c, services } = servicesModel();
    const pending = cell(c, 'Maybe', services, { pending: true });
    expect(canDeleteFromDrawer(services)).toBe(true);
    expect(canDeleteFromDrawer(rootOf(c))).toBe(false);
    expect(canDeleteFromDrawer(pending)).toBe(false);

    store.ui.drawerNode = services;
    const shown = render(<Drawer />);
    expect(shown.container.querySelector('#drDelete')?.textContent).toBe('Delete');
    shown.unmount();

    store.ui.drawerNode = c.root;
    const root = render(<Drawer />);
    expect(root.container.querySelector('#drDelete')).toBeNull();
    root.unmount();

    store.ui.drawerNode = pending;
    const wait = render(<Drawer />);
    expect(wait.container.querySelector('#drDelete')).toBeNull();
    wait.unmount();
  });

  it('opens the same confirmation from the drawer', () => {
    const { services } = servicesModel();
    store.ui.drawerNode = services;
    const dialog = render(<Dialog />);
    const drawer = render(<Drawer />);
    act(() => drawer.container.querySelector<HTMLButtonElement>('#drDelete')?.click());
    expect(dialog.container.querySelector('.dlg .dh b')?.textContent).toBe('Delete Services?');
    expect(dialog.container.querySelector('.dlg .df .btn.danger')?.textContent).toBe('Propose deletion');
  });
});
