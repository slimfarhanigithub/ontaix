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
  s.lineageNode = null;
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
const items = () => [...document.querySelectorAll('#drMoreMenu [role^="menuitem"]')] as HTMLButtonElement[];
const openMenu = () => act(() => more().click());
const key = (k: string) => act(() => fireEvent.keyDown(document.activeElement as Element, { key: k }));
/** The menu's children in order: an item's id, or `|` for a divider. */
const layout = () => [...(menu()?.children ?? [])].map((el) => (el.getAttribute('role') === 'separator' ? '|' : el.id));

describe('drawer More actions menu', () => {
  afterEach(() => {
    store.ui.dialogs = [];
    store.ui.drawerNode = null;
    store.ui.expanding = null;
    store.ui.newBox = null;
    store.ui.toasts = [];
    store.s.SKIP = false;
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('is the only button of the action row, closed', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    const { container } = render(<Drawer />);
    expect([...container.querySelectorAll('.drawer .actions button')].map((b) => b.id)).toEqual(['drMore']);
    expect(container.querySelector('#drGrow')).toBeNull();
    expect(container.querySelector('#drLineage')).toBeNull();
    const btn = more();
    expect(btn.getAttribute('data-ox-new')).toBe('');
    expect(btn.getAttribute('aria-label')).toBe('More actions');
    expect(btn.getAttribute('aria-haspopup')).toBe('menu');
    expect(btn.getAttribute('aria-expanded')).toBe('false');
    expect(btn.textContent).toBe('⋯');
    expect(menu()).toBeNull();
  });

  it('opens with every action in three groups, an icon per item, the focus on the first; Escape closes and gives the focus back', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    render(<Drawer />);
    openMenu();
    expect(more().getAttribute('aria-expanded')).toBe('true');
    expect(more().getAttribute('aria-controls')).toBe('drMoreMenu');
    const m = menu();
    expect(m?.getAttribute('role')).toBe('menu');
    expect(m?.getAttribute('aria-label')).toBe('More actions');
    expect(m?.parentElement).toBe(document.body);
    expect(m?.getAttribute('data-place')).toBe('below');
    expect(layout()).toEqual(['drGrow', 'drLineage', 'drExpand', '|', 'drRename', 'drMove', '|', 'drDelete']);
    expect(items().map((b) => [b.getAttribute('role'), b.textContent])).toEqual([
      ['menuitem', 'Grow a concept from it'],
      ['menuitemcheckbox', 'Lineage'],
      ['menuitem', 'Expand…'],
      ['menuitem', 'Rename…'],
      ['menuitem', 'Move to domain…'],
      ['menuitem', 'Delete'],
    ]);
    for (const it of items()) {
      expect(it.getAttribute('tabindex')).toBe('-1');
      expect(it.firstElementChild?.tagName).toBe('svg');
      expect(it.firstElementChild?.getAttribute('class')).toBe('ico');
      expect(it.firstElementChild?.getAttribute('aria-hidden')).toBe('true');
      expect(it.querySelector('.label')?.textContent).toBe(it.textContent);
    }
    expect(document.getElementById('drDelete')?.className).toBe('danger');
    expect(m?.querySelectorAll('[role="separator"]')).toHaveLength(2);
    expect(document.activeElement?.id).toBe('drGrow');
    const escape = vi.spyOn(store, 'escape');
    key('Escape');
    expect(menu()).toBeNull();
    expect(more().getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement?.id).toBe('drMore');
    expect(escape).not.toHaveBeenCalled();
  });

  it('Grow a concept from it opens the new-concept box on the cell and closes the menu', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    render(<Drawer />);
    const grow = vi.spyOn(store, 'openNewBox');
    openMenu();
    act(() => document.getElementById('drGrow')?.click());
    expect(grow).toHaveBeenCalledTimes(1);
    expect(grow.mock.calls[0][0]).toBe(plant);
    expect(menu()).toBeNull();
    expect(document.activeElement?.id).toBe('drMore');
  });

  it('Lineage is a check item that follows the lineage focus and toggles it', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    render(<Drawer />);
    openMenu();
    const lineage = () => document.getElementById('drLineage') as HTMLButtonElement;
    expect(lineage().getAttribute('aria-checked')).toBe('false');
    expect(lineage().hasAttribute('aria-pressed')).toBe(false);
    expect(lineage().querySelector('.on')).toBeNull();
    act(() => lineage().click());
    expect(menu()).toBeNull();
    expect(store.s.lineageNode).toBe(plant);
    expect(document.getElementById('drLine')?.style.display).toBe('');
    openMenu();
    expect(lineage().getAttribute('aria-checked')).toBe('true');
    expect(lineage().querySelector('svg.on')?.getAttribute('aria-hidden')).toBe('true');
    expect(lineage().textContent).toBe('Lineage');
    act(() => lineage().click());
    expect(store.s.lineageNode).toBeNull();
    expect(document.getElementById('drLine')?.style.display).toBe('none');
    openMenu();
    expect(lineage().getAttribute('aria-checked')).toBe('false');
  });

  it('Down, Up, Home and End move the focus around the items; Tab closes', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    render(<Drawer />);
    openMenu();
    key('ArrowDown');
    expect(document.activeElement?.id).toBe('drLineage');
    key('End');
    expect(document.activeElement?.id).toBe('drDelete');
    key('ArrowDown');
    expect(document.activeElement?.id).toBe('drGrow');
    key('ArrowUp');
    expect(document.activeElement?.id).toBe('drDelete');
    key('Home');
    expect(document.activeElement?.id).toBe('drGrow');
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
    expect(document.activeElement?.id).toBe('drGrow');
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

  it('each dialog item opens the dialog of its action, closes the menu and leaves the focus on the button', () => {
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

  it('offers Grow and Expand for the company root, Grow and Lineage for a pending cell, and no button for a source', () => {
    const { c, plant } = model();
    const pending = addNode(store.s, { label: 'Maybe', kind: 'concept', company: c, parent: plant, pending: true, sid: 'c-maybe' });
    const source = addNode(store.s, { label: 'SAP', kind: 'source', company: c, sub: 'ERP' });
    store.ui.drawerNode = c.root;
    const root = render(<Drawer />);
    openMenu();
    expect(layout()).toEqual(['drGrow', 'drExpand']);
    root.unmount();
    store.ui.drawerNode = pending;
    const waiting = render(<Drawer />);
    openMenu();
    expect(layout()).toEqual(['drGrow', 'drLineage']);
    waiting.unmount();
    store.ui.drawerNode = source;
    const shown = render(<Drawer />);
    expect(shown.container.querySelector('#drMore')).toBeNull();
    expect(shown.container.querySelector('.drawer .actions')?.children).toHaveLength(0);
    shown.unmount();
  });

  it('while an expansion runs, Expand… waits with the ring in place of its icon, the button shows the ring and the focus skips it', () => {
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
    expect(expand.getAttribute('aria-busy')).toBe('true');
    expect(expand.firstElementChild?.className).toBe('spin');
    expect(expand.querySelector('svg')).toBeNull();
    expect(expand.textContent).toBe('Expand…');
    expect(document.activeElement?.id).toBe('drGrow');
    key('ArrowDown');
    expect(document.activeElement?.id).toBe('drLineage');
    key('ArrowDown');
    expect(document.activeElement?.id).toBe('drRename');
    act(() => {
      store.ui.expanding = null;
      store.bump();
    });
    expect(more().firstElementChild?.className).toBe('');
    expect(expand.disabled).toBe(false);
    expect(expand.firstElementChild?.tagName).toBe('svg');
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

  it('hangs under the button, right edges aligned, and moves above it when the viewport has no room below', () => {
    const { plant } = model();
    store.ui.drawerNode = plant;
    render(<Drawer />);
    const rect = (x: number, y: number, w: number, h: number) => ({ x, y, width: w, height: h, top: y, left: x, right: x + w, bottom: y + h, toJSON: () => '' });
    vi.spyOn(HTMLButtonElement.prototype, 'getBoundingClientRect').mockReturnValue(rect(290, 400, 34, 34));
    vi.spyOn(HTMLDivElement.prototype, 'offsetWidth', 'get').mockReturnValue(200);
    vi.spyOn(HTMLDivElement.prototype, 'offsetHeight', 'get').mockReturnValue(240);
    openMenu();
    expect(menu()?.style.top).toBe('440px');
    expect(menu()?.style.left).toBe('124px');
    expect(menu()?.getAttribute('data-place')).toBe('below');
    key('Escape');
    vi.spyOn(HTMLButtonElement.prototype, 'getBoundingClientRect').mockReturnValue(rect(290, window.innerHeight - 60, 34, 34));
    openMenu();
    expect(menu()?.style.top).toBe(`${window.innerHeight - 60 - 6 - 240}px`);
    expect(menu()?.getAttribute('data-place')).toBe('above');
    key('Escape');
    vi.spyOn(HTMLButtonElement.prototype, 'getBoundingClientRect').mockReturnValue(rect(100, 400, 34, 34));
    openMenu();
    expect(menu()?.style.left).toBe('8px');
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
