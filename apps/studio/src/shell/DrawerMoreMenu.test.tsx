import { act, fireEvent, render } from '@testing-library/react';

import { DOMAIN_TEMPLATES } from '../canvas/constants';
import { addCompany, addNode, domainOf } from '../canvas/state';
import type { Company, Node } from '../canvas/types';
import { store } from '../store/store';
import { Dialog } from './Dialog';
import { Drawer } from './Drawer';

function model(): { c: Company; plant: Node; line: Node } {
  const s = store.s;
  s.nodes.length = 0;
  s.links.length = 0;
  s.companies.length = 0;
  s.DOMAINS = [];
  s.selected.clear();
  s.SKIP = false;
  store.ui.domains = DOMAIN_TEMPLATES.map((t, position) => ({ key: t.key, name: t.name, owner: t.owner, color: t.color, defaultColor: t.color, template: true, position, revision: 0 }));
  const c = addCompany(s, 'Northwind Industries', '');
  c.sid = 'co-1';
  if (c.root) c.root.sid = 'root-1';
  const plant = addNode(s, { label: 'Plant', kind: 'concept', company: c, domain: domainOf(s, 'production', c), parent: c.root ?? undefined, sid: 'c-plant' });
  const line = addNode(s, { label: 'Line', kind: 'concept', company: c, domain: domainOf(s, 'production', c), parent: plant, sid: 'c-line' });
  return { c, plant, line };
}

const more = () => document.getElementById('drMore') as HTMLButtonElement;
const menu = () => document.getElementById('drMoreMenu');
const items = () => [...document.querySelectorAll('#drMoreMenu [role="menuitem"]')] as HTMLButtonElement[];
const openMenu = () => act(() => more().click());
const key = (k: string) => act(() => fireEvent.keyDown(document.activeElement as Element, { key: k }));

describe('drawer More actions menu', () => {
  afterEach(() => {
    store.ui.dialogs = [];
    store.ui.drawerNode = null;
    store.ui.expanding = null;
    store.ui.toasts = [];
    store.s.SKIP = false;
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('keeps the reference buttons in the row and adds one More actions button, closed', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    const { container } = render(<Drawer />);
    expect([...container.querySelectorAll('.drawer .actions button')].map((b) => b.id)).toEqual(['drGrow', 'drLineage', 'drMore']);
    const btn = more();
    expect(btn.getAttribute('data-ox-new')).toBe('');
    expect(btn.getAttribute('aria-label')).toBe('More actions');
    expect(btn.getAttribute('aria-haspopup')).toBe('menu');
    expect(btn.getAttribute('aria-expanded')).toBe('false');
    expect(btn.textContent).toBe('⋯');
    expect(menu()).toBeNull();
  });

  it('opens with the items in order, a divider before Delete, the focus on the first item; Escape closes and gives the focus back', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    render(<Drawer />);
    openMenu();
    expect(more().getAttribute('aria-expanded')).toBe('true');
    expect(more().getAttribute('aria-controls')).toBe('drMoreMenu');
    const m = menu();
    expect(m?.getAttribute('role')).toBe('menu');
    expect(m?.parentElement).toBe(document.body);
    expect(items().map((b) => [b.id, b.textContent])).toEqual([
      ['drExpand', 'Expand…'],
      ['drRename', 'Rename…'],
      ['drMove', 'Move to domain…'],
      ['drDelete', 'Delete'],
    ]);
    expect(document.getElementById('drDelete')?.className).toBe('danger');
    expect(document.getElementById('drDelete')?.previousElementSibling?.getAttribute('role')).toBe('separator');
    expect(m?.querySelectorAll('[role="separator"]')).toHaveLength(1);
    expect(document.activeElement?.id).toBe('drExpand');
    const escape = vi.spyOn(store, 'escape');
    key('Escape');
    expect(menu()).toBeNull();
    expect(more().getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement?.id).toBe('drMore');
    expect(escape).not.toHaveBeenCalled();
  });

  it('Down, Up, Home and End move the focus around the items; Tab closes', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    render(<Drawer />);
    openMenu();
    key('ArrowDown');
    expect(document.activeElement?.id).toBe('drRename');
    key('End');
    expect(document.activeElement?.id).toBe('drDelete');
    key('ArrowDown');
    expect(document.activeElement?.id).toBe('drExpand');
    key('ArrowUp');
    expect(document.activeElement?.id).toBe('drDelete');
    key('Home');
    expect(document.activeElement?.id).toBe('drExpand');
    key('Tab');
    expect(menu()).toBeNull();
    expect(document.activeElement?.id).toBe('drMore');
  });

  it('Down on the button opens it; a press outside closes it and gives the focus back', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    render(<Drawer />);
    act(() => more().focus());
    key('ArrowDown');
    expect(menu()).not.toBeNull();
    expect(document.activeElement?.id).toBe('drExpand');
    act(() => {
      fireEvent.pointerDown(document.getElementById('drRename') as Element);
    });
    expect(menu()).not.toBeNull();
    act(() => {
      fireEvent.pointerDown(document.body);
    });
    expect(menu()).toBeNull();
    expect(document.activeElement?.id).toBe('drMore');
  });

  it('each item opens the dialog of its action, closes the menu and leaves the focus on the button', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    const dialog = render(<Dialog />);
    render(<Drawer />);
    const title = () => dialog.container.querySelector('.dlg .dh b')?.textContent;
    const pick = (id: string) => {
      openMenu();
      act(() => document.getElementById(id)?.click());
      expect(menu()).toBeNull();
      expect(document.activeElement?.id).toBe('drMore');
    };
    pick('drExpand');
    expect(title()).toBe('Expand Plant');
    act(() => store.closeDialog());
    pick('drRename');
    expect(title()).toBe('Rename Plant');
    act(() => store.closeDialog());
    pick('drMove');
    expect(title()).toBe('Move Plant');
    act(() => store.closeDialog());
    pick('drDelete');
    expect(title()).toBe('Delete Plant?');
    expect(dialog.container.querySelector('.dlg .df .btn.danger')?.textContent).toBe('Propose deletion');
  });

  it('offers Expand alone for the company root, and no button for a pending cell or a source', () => {
    const { c, plant } = model();
    const pending = addNode(store.s, { label: 'Maybe', kind: 'concept', company: c, parent: plant, pending: true, sid: 'c-maybe' });
    const source = addNode(store.s, { label: 'SAP', kind: 'source', company: c, sub: 'ERP' });
    store.ui.drawerNode = c.root;
    const root = render(<Drawer />);
    openMenu();
    expect(items().map((b) => b.id)).toEqual(['drExpand']);
    expect(menu()?.querySelector('[role="separator"]')).toBeNull();
    root.unmount();
    for (const n of [pending, source]) {
      store.ui.drawerNode = n;
      const shown = render(<Drawer />);
      expect(shown.container.querySelector('#drMore')).toBeNull();
      shown.unmount();
    }
  });

  it('while an expansion runs, Expand… waits with the ring, the button shows the ring and the focus skips to Rename…', () => {
    vi.useFakeTimers();
    const { plant } = model();
    store.ui.drawerNode = plant;
    render(<Drawer />);
    act(() => {
      store.ui.expanding = plant;
      store.bump();
    });
    act(() => vi.advanceTimersByTime(250));
    expect(more().firstElementChild?.className).toBe('spin');
    expect(more().getAttribute('aria-busy')).toBe('true');
    expect(more().disabled).toBe(false);
    openMenu();
    const expand = document.getElementById('drExpand') as HTMLButtonElement;
    expect(expand.disabled).toBe(true);
    expect(expand.firstElementChild?.className).toBe('spin');
    expect(expand.textContent).toBe('Expand…');
    expect(document.activeElement?.id).toBe('drRename');
    key('ArrowUp');
    expect(document.activeElement?.id).toBe('drDelete');
    act(() => {
      store.ui.expanding = null;
      store.bump();
    });
    expect(more().firstElementChild?.className).toBe('');
    expect(expand.disabled).toBe(false);
  });

  it('closes when another cell is selected and when the drawer closes', () => {
    const { plant, line } = model();
    store.ui.drawerNode = plant;
    render(<Drawer />);
    openMenu();
    act(() => store.openDrawer(line));
    expect(menu()).toBeNull();
    expect(more().getAttribute('aria-expanded')).toBe('false');
    openMenu();
    act(() => store.closeDrawer());
    expect(menu()).toBeNull();
    expect(document.getElementById('drMore')).toBeNull();
  });

  it('skips its fade while Skip animation is on', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    render(<Drawer />);
    openMenu();
    expect(menu()?.style.animation).toBe('');
    key('Escape');
    store.s.SKIP = true;
    openMenu();
    expect(menu()?.style.animation).toBe('none');
  });
});
