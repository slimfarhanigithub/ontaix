/**
 * The drawer's More actions button (`#drMore`) and its menu: the owner's additions to the
 * reference's action row (Expand, Rename, Move to domain and Delete) behind one square `⋯`
 * button, so the row keeps the reference's two buttons at their width. The menu is drawn in the
 * body, under the button with their right edges aligned, because the drawer scrolls and would
 * clip a menu placed inside it. Each item opens the dialog its action opens from the admin
 * portal; the button takes the focus first, so the dialog gives it back there when it closes.
 */
import { Fragment, useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { createPortal } from 'react-dom';

import { deleteNodeDialog, moveDialog, renameDialog } from '../admin/actions';
import { canDeleteFromDrawer } from '../admin/conceptDeletion';
import type { Node } from '../canvas/types';
import { useStore } from './dom';
import { canExpandFromDrawer, openExpandDialog } from './ExpandDialog';

/** Space between the button and the menu, in pixels. */
const MENU_GAP = 6;

export interface MoreMenuItem {
  id: string;
  label: string;
  /** Rendered in the reference's conflict red after a divider. */
  danger?: boolean;
  /** Disabled, showing the waiting ring before its label. */
  waiting?: boolean;
  act: () => void;
}

/** The items the menu offers for a cell, in order; none for a source or a pending cell. */
export function moreMenuItems(n: Node, expanding: boolean): MoreMenuItem[] {
  const items: MoreMenuItem[] = [];
  if (canExpandFromDrawer(n)) items.push({ id: 'drExpand', label: 'Expand…', waiting: expanding, act: () => openExpandDialog(n) });
  if (canDeleteFromDrawer(n)) {
    items.push({ id: 'drRename', label: 'Rename…', act: () => renameDialog(n) });
    items.push({ id: 'drMove', label: 'Move to domain…', act: () => moveDialog(n) });
    items.push({ id: 'drDelete', label: 'Delete', danger: true, act: () => deleteNodeDialog(n) });
  }
  return items;
}

const ENABLED_ITEMS = '[role="menuitem"]:not(:disabled)';

export function DrawerMoreMenu({ node, expanding }: { node: Node; expanding: boolean }) {
  const st = useStore();
  const items = moreMenuItems(node, expanding);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, right: 0 });
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  const close = (focusButton: boolean) => {
    setOpen(false);
    if (focusButton) btn.current?.focus();
  };

  const show = () => {
    const r = btn.current?.getBoundingClientRect();
    if (r) setPos({ top: r.bottom + MENU_GAP, right: Math.max(0, window.innerWidth - r.right) });
    setOpen(true);
  };

  // The first enabled item takes the focus once the menu is in the DOM.
  useEffect(() => {
    if (open) menu.current?.querySelector<HTMLElement>(ENABLED_ITEMS)?.focus();
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
      show();
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

  const firstDanger = items.findIndex((it) => it.danger);
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
        onClick={() => (open ? close(true) : show())}
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
              style={{ top: pos.top, right: pos.right, animation: st.s.SKIP ? 'none' : undefined }}
              onKeyDown={onMenuKey}
            >
              {items.map((it, i) => (
                <Fragment key={it.id}>
                  {i > 0 && i === firstDanger ? <div className="sep" role="separator"></div> : null}
                  <button
                    type="button"
                    role="menuitem"
                    id={it.id}
                    className={it.danger ? 'danger' : undefined}
                    tabIndex={-1}
                    disabled={it.waiting}
                    aria-busy={it.waiting ? 'true' : undefined}
                    onClick={() => activate(it)}
                  >
                    {it.waiting ? <span className="spin"></span> : null}
                    {it.label}
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
