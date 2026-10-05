/**
 * A More actions button (`⋯`) and its menu, shared by the cell drawer and the admin lists' rows.
 * The menu is drawn in the body, because a scrolling drawer or list would clip a menu placed
 * inside it; it hangs under the button with their right edges aligned, and moves up or sideways
 * when it would leave the viewport. The button takes the focus first, so a dialog an item opens
 * gives it back there when it closes. Items stand in groups separated by dividers; a danger item
 * reads in red; a waiting item is disabled and shows the ring in place of its icon.
 */
import { Fragment, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

/** Space between the button and the menu, in pixels. */
const MENU_GAP = 6;
/** The least space kept between the menu and the viewport's edges, in pixels. */
const VIEWPORT_EDGE = 8;

export type MoreMenuIcon = 'grow' | 'lineage' | 'expand' | 'rename' | 'move' | 'delete' | 'edit' | 'people' | 'key' | 'link' | 'open' | 'power';

export interface MoreMenuItem {
  id?: string;
  label: string;
  icon?: MoreMenuIcon;
  /** Items of one group stand together; a divider separates two groups. */
  group: number;
  /** A toggle, showing a check mark while on. */
  checked?: boolean;
  /** Rendered in red. */
  danger?: boolean;
  /** Disabled, showing the waiting ring in place of its icon. */
  waiting?: boolean;
  /** Disabled for another reason than waiting. */
  disabled?: boolean;
  /** Extra attributes on the item, such as the `data-fn` the admin lists name their actions by. */
  attrs?: Record<string, string>;
  act: () => void;
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
  edit: <path d="M3 13h2.8l7-7-2.8-2.8-7 7V13zM9.2 4l2.8 2.8" />,
  move: <path d="M2.5 8h7M7 5.5L9.5 8 7 10.5M11 3.5h2.5v9H11" />,
  delete: <path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5M6.8 7.2v3.8M9.2 7.2v3.8" />,
  people: (
    <>
      <circle cx="6" cy="5.5" r="2.3" />
      <path d="M2.5 13c0-2.4 1.6-3.8 3.5-3.8s3.5 1.4 3.5 3.8M10.5 3.8a2.3 2.3 0 010 4.4M11 9.4c1.5.4 2.5 1.6 2.5 3.6" />
    </>
  ),
  key: (
    <>
      <circle cx="5.5" cy="10.5" r="2.5" />
      <path d="M7.3 8.7L13 3M10.5 5.5L12 7M11.8 4.2l1.3 1.3" />
    </>
  ),
  link: <path d="M6.5 9.5a2.5 2.5 0 003.5 0l2-2a2.5 2.5 0 00-3.5-3.5l-1 1M9.5 6.5a2.5 2.5 0 00-3.5 0l-2 2a2.5 2.5 0 003.5 3.5l1-1" />,
  open: <path d="M9.5 3H13v3.5M13 3L7.5 8.5M11 9.5V13H3V5h3.5" />,
  power: <path d="M8 2.5v5.5M4.3 5.3a5.2 5.2 0 107.4 0" />,
};

const CHECK = <path d="M3.5 8.5l2.8 2.8L12.5 5" />;

const ENABLED_ITEMS = '[role^="menuitem"]:not(:disabled)';

interface MenuPosition {
  top: number;
  left: number;
  /** Whether the menu hangs under the button; above it when the viewport has no room below. */
  below: boolean;
}

export interface MoreMenuProps {
  /** The button's id. */
  id: string;
  /** The menu's id, named by `aria-controls` while open. */
  menuId: string;
  /** The accessible name of the button and the menu. */
  label: string;
  items: MoreMenuItem[];
  /** The button's class; `more` by default. */
  className?: string;
  /** Marks the button as an owner addition absent from the reference. */
  oxNew?: boolean;
  /** The button shows the waiting ring in place of its dots. */
  waiting?: boolean;
  /** Whether the menu opens without its entrance animation, read when it opens. */
  skipAnimation?: () => boolean;
}

export function MoreMenu({ id, menuId, label, items, className = 'more', oxNew, waiting, skipAnimation }: MoreMenuProps) {
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
      // Whatever holds the menu (the canvas, the admin portal) must not see this Escape.
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
        id={id}
        className={className}
        data-ox-new={oxNew ? '' : undefined}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-busy={waiting ? 'true' : undefined}
        onClick={(e) => {
          // A list row that opens on click must not see the button or its items.
          e.stopPropagation();
          open ? close(true) : setOpen(true);
        }}
        onKeyDown={onButtonKey}
      >
        {waiting ? <span className="spin"></span> : <span aria-hidden="true">⋯</span>}
      </button>
      {open
        ? createPortal(
            <div
              ref={menu}
              id={menuId}
              className="dr-menu"
              role="menu"
              aria-label={label}
              data-place={pos.below ? 'below' : 'above'}
              style={{ top: pos.top, left: pos.left, animation: skipAnimation?.() ? 'none' : undefined }}
              onClick={(e) => e.stopPropagation()}
              onKeyDown={onMenuKey}
            >
              {items.map((it, i) => (
                <Fragment key={it.id ?? it.label}>
                  {i > 0 && it.group !== items[i - 1].group ? <div className="sep" role="separator"></div> : null}
                  <button
                    type="button"
                    role={it.checked === undefined ? 'menuitem' : 'menuitemcheckbox'}
                    id={it.id}
                    className={it.danger ? 'danger' : undefined}
                    tabIndex={-1}
                    disabled={it.waiting || it.disabled}
                    aria-busy={it.waiting ? 'true' : undefined}
                    aria-checked={it.checked === undefined ? undefined : it.checked}
                    onClick={() => activate(it)}
                    {...it.attrs}
                  >
                    {it.waiting ? (
                      <span className="spin"></span>
                    ) : it.icon ? (
                      <svg className="ico" viewBox="0 0 16 16" aria-hidden="true">
                        {ICONS[it.icon]}
                      </svg>
                    ) : null}
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
