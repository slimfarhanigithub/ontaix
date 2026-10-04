/**
 * The drawer's More actions button (`#drMore`), the only button of the drawer's action row, and
 * its menu, which holds every action on a cell: Grow a concept from it, Lineage (a toggle) and
 * Expand; Rename and Move to domain; Delete. Each item keeps the id, visibility rule and effect
 * its action has elsewhere. The menu is drawn in the body, because the drawer scrolls and would
 * clip a menu placed inside it; it hangs under the button with their right edges aligned, and
 * moves up or sideways when it would leave the viewport. The button takes the focus first, so a
 * dialog an item opens gives it back there when it closes.
 */
import { Fragment, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { deleteNodeDialog, moveDialog, renameDialog } from '../admin/actions';
import { canDeleteFromDrawer } from '../admin/conceptDeletion';
import type { Node } from '../canvas/types';
import type { store } from '../store/store';
import { useStore } from './dom';
import { canExpandFromDrawer, openExpandDialog } from './ExpandDialog';

/** Space between the button and the menu, in pixels. */
const MENU_GAP = 6;
/** The least space kept between the menu and the viewport's edges, in pixels. */
const VIEWPORT_EDGE = 8;

export type MoreMenuIcon = 'grow' | 'lineage' | 'expand' | 'rename' | 'move' | 'delete';

export interface MoreMenuItem {
  id: string;
  label: string;
  icon: MoreMenuIcon;
  /** Items of one group stand together; a divider separates two groups. */
  group: number;
  /** A toggle, showing a check mark while on. */
  checked?: boolean;
  /** Rendered in the reference's conflict red. */
  danger?: boolean;
  /** Disabled, showing the waiting ring in place of its icon. */
  waiting?: boolean;
  act: () => void;
}

/** The items the menu offers for a cell, in order and in groups; none for a source. */
export function moreMenuItems(st: typeof store, n: Node, expanding: boolean): MoreMenuItem[] {
  const items: MoreMenuItem[] = [];
  if (n.kind !== 'source')
    items.push({
      id: 'drGrow',
      label: 'Grow a concept from it',
      icon: 'grow',
      group: 1,
      act: () => {
        const v = st.renderer?.v;
        st.openNewBox(n, (v ? v.W : innerWidth) * 0.35, (v ? v.H : innerHeight) * 0.4);
      },
    });
  if (n.kind === 'concept') items.push({ id: 'drLineage', label: 'Lineage', icon: 'lineage', group: 1, checked: st.s.lineageNode === n, act: () => st.toggleLineage() });
  if (canExpandFromDrawer(n)) items.push({ id: 'drExpand', label: 'Expand…', icon: 'expand', group: 1, waiting: expanding, act: () => openExpandDialog(n) });
  if (canDeleteFromDrawer(n)) {
    items.push({ id: 'drRename', label: 'Rename…', icon: 'rename', group: 2, act: () => renameDialog(n) });
    items.push({ id: 'drMove', label: 'Move to domain…', icon: 'move', group: 2, act: () => moveDialog(n) });
    items.push({ id: 'drDelete', label: 'Delete', icon: 'delete', group: 3, danger: true, act: () => deleteNodeDialog(n) });
  }
  return items;
}

/** Line icons on the reference's 16-unit grid, stroked in the current colour. */
const ICONS: Record<MoreMenuIcon, ReactNode> = {
  grow: (
    <>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 5.5v5M5.5 8h5" />
    </>
  ),
  lineage: (
    <>
      <circle cx="8" cy="3" r="1.3" />
      <circle cx="4.5" cy="11.5" r="1.3" />
      <circle cx="11.5" cy="11.5" r="1.3" />
      <path d="M8 4.3v2.2M8 6.5H4.5v3.7M8 6.5h3.5v3.7" />
    </>
  ),
  expand: <path d="M9.5 3H13v3.5M13 3L9 7M6.5 13H3V9.5M3 13l4-4" />,
  rename: <path d="M3 13h2.8l7-7-2.8-2.8-7 7V13zM9.2 4l2.8 2.8" />,
  move: <path d="M2.5 8h7M7 5.5L9.5 8 7 10.5M11 3.5h2.5v9H11" />,
  delete: <path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5M6.8 7.2v3.8M9.2 7.2v3.8" />,
};

const CHECK = <path d="M3.5 8.5l2.8 2.8L12.5 5" />;

const ENABLED_ITEMS = '[role^="menuitem"]:not(:disabled)';

interface MenuPosition {
  top: number;
  left: number;
  /** Whether the menu hangs under the button; above it when the viewport has no room below. */
  below: boolean;
}

export function DrawerMoreMenu({ node, expanding }: { node: Node; expanding: boolean }) {
  const st = useStore();
  const items = moreMenuItems(st, node, expanding);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<MenuPosition>({ top: 0, left: 0, below: true });
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  const close = (focusButton: boolean) => {
    setOpen(false);
    if (focusButton) btn.current?.focus();
  };

  // Once the menu is in the DOM, before it is painted: under the button with their right edges
  // aligned, moved up when it would run past the bottom of the viewport and sideways when it would
  // run past either side; then the first enabled item takes the focus.
  useLayoutEffect(() => {
    if (!open) return;
    const r = btn.current?.getBoundingClientRect();
    const m = menu.current;
    if (r && m) {
      const w = m.offsetWidth,
        h = m.offsetHeight;
      const below = r.bottom + MENU_GAP + h <= window.innerHeight - VIEWPORT_EDGE;
      const top = below ? r.bottom + MENU_GAP : Math.max(VIEWPORT_EDGE, r.top - MENU_GAP - h);
      const left = Math.max(VIEWPORT_EDGE, Math.min(r.right - w, window.innerWidth - VIEWPORT_EDGE - w));
      setPos({ top, left, below });
    }
    m?.querySelector<HTMLElement>(ENABLED_ITEMS)?.focus();
  }, [open]);

  // A press outside the button and the menu closes it and gives the focus back to the button;
  // a resize or a scroll, which move the button, close it too.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      const t = e.target as globalThis.Node | null;
      if (btn.current?.contains(t) || menu.current?.contains(t)) return;
      close(true);
    };
    const onMove = () => close(false);
    document.addEventListener('pointerdown', onPointerDown, true);
    window.addEventListener('resize', onMove);
    window.addEventListener('scroll', onMove, true);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown, true);
      window.removeEventListener('resize', onMove);
      window.removeEventListener('scroll', onMove, true);
    };
  }, [open]);

  if (!items.length) return null;

  const activate = (item: MoreMenuItem) => {
    close(true);
    item.act();
  };

  const onButtonKey = (e: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'ArrowDown' && !open) {
      e.preventDefault();
      setOpen(true);
    }
  };

  const onMenuKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const enabled = [...(menu.current?.querySelectorAll<HTMLElement>(ENABLED_ITEMS) ?? [])];
    const at = enabled.indexOf(document.activeElement as HTMLElement);
    const go = (i: number) => {
      e.preventDefault();
      enabled[(i + enabled.length) % enabled.length]?.focus();
    };
    if (e.key === 'ArrowDown') go(at + 1);
    else if (e.key === 'ArrowUp') go(at < 0 ? enabled.length - 1 : at - 1);
    else if (e.key === 'Home') go(0);
    else if (e.key === 'End') go(enabled.length - 1);
    else if (e.key === 'Escape') {
      // The canvas's own Escape, which closes the drawer, must not see this one.
      e.preventDefault();
      e.stopPropagation();
      close(true);
    } else if (e.key === 'Tab') close(true);
  };

  return (
    <>
      <button
        ref={btn}
        type="button"
        id="drMore"
        className="more"
        data-ox-new=""
        aria-label="More actions"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? 'drMoreMenu' : undefined}
        aria-busy={expanding ? 'true' : undefined}
        onClick={() => (open ? close(true) : setOpen(true))}
        onKeyDown={onButtonKey}
      >
        {expanding ? <span className="spin"></span> : <span aria-hidden="true">⋯</span>}
      </button>
      {open
        ? createPortal(
            <div
              ref={menu}
              id="drMoreMenu"
              className="dr-menu"
              role="menu"
              aria-label="More actions"
              data-place={pos.below ? 'below' : 'above'}
              style={{ top: pos.top, left: pos.left, animation: st.s.SKIP ? 'none' : undefined }}
              onKeyDown={onMenuKey}
            >
              {items.map((it, i) => (
                <Fragment key={it.id}>
                  {i > 0 && it.group !== items[i - 1].group ? <div className="sep" role="separator"></div> : null}
                  <button
                    type="button"
                    role={it.checked === undefined ? 'menuitem' : 'menuitemcheckbox'}
                    id={it.id}
                    className={it.danger ? 'danger' : undefined}
                    tabIndex={-1}
                    disabled={it.waiting}
                    aria-busy={it.waiting ? 'true' : undefined}
                    aria-checked={it.checked === undefined ? undefined : it.checked}
                    onClick={() => activate(it)}
                  >
                    {it.waiting ? (
                      <span className="spin"></span>
                    ) : (
                      <svg className="ico" viewBox="0 0 16 16" aria-hidden="true">
                        {ICONS[it.icon]}
                      </svg>
                    )}
                    <span className="label">{it.label}</span>
                    {it.checked ? (
                      <svg className="on" viewBox="0 0 16 16" aria-hidden="true">
                        {CHECK}
                      </svg>
                    ) : null}
                  </button>
                </Fragment>
              ))}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
