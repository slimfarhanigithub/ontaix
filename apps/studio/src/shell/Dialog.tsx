/**
 * Modal dialogs: title, sub, body, footer buttons, closed with ×, the backdrop or Escape.
 * Markup and behaviour from reference/ontaix-studio-reference.html lines 916-919 (`dialog`).
 * Dialogs stack: one opened from another sits on top of it, as appended elements do in the
 * reference. A dialog is named by its title, keeps Tab inside itself, closes with Escape wherever
 * the focus is, and gives focus back to the element that opened it when it closes.
 */
import { Fragment, useEffect, useId, useLayoutEffect, useRef, type KeyboardEvent, type ReactNode, type RefObject } from 'react';

import { useBusyAction } from './busy';
import { useStore } from './dom';

/** Elements Tab can reach inside a dialog or the admin portal. */
const TABBABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * Keeps Tab inside `root`: from the last reachable element to the first, from the first back to
 * the last with Shift, and from anywhere outside to the first. Returns true when it moved focus.
 */
export function trapTab(e: { key: string; shiftKey: boolean; preventDefault(): void }, root: HTMLElement | null): boolean {
  if (e.key !== 'Tab' || !root) return false;
  const items = Array.from(root.querySelectorAll<HTMLElement>(TABBABLE)).filter((el) => !el.closest('[hidden]') && el.style.display !== 'none');
  if (!items.length) return false;
  const first = items[0],
    last = items[items.length - 1];
  const active = document.activeElement as HTMLElement | null;
  const inside = !!active && root.contains(active) && items.includes(active);
  let target: HTMLElement | null = null;
  if (!inside) target = e.shiftKey ? last : first;
  else if (e.shiftKey && active === first) target = last;
  else if (!e.shiftKey && active === last) target = first;
  if (!target) return false;
  e.preventDefault();
  target.focus();
  return true;
}

/**
 * Remembers the focused element while `open` turns true and gives focus back to it when `open`
 * turns false or the caller unmounts, if the focus is then nowhere or inside `root`.
 */
export function useFocusReturn(open: boolean, root: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    if (!open) return;
    const from = document.activeElement as HTMLElement | null;
    const el = root.current;
    return () => {
      const active = document.activeElement;
      const lost = !active || active === document.body || !active.isConnected || (!!el && el.contains(active));
      if (from && from !== document.body && from.isConnected && lost) from.focus();
    };
  }, [open, root]);
}

export interface DialogButton {
  label: string;
  cls?: string;
  /** Returns false to keep the dialog open; a returned promise keeps it open, its button waiting, until it settles. */
  onClick?: (root: HTMLDivElement, close: () => void) => boolean | void | Promise<boolean | void>;
  keep?: boolean;
}

export interface DialogSpec {
  title: string;
  sub?: string;
  body: ReactNode;
  buttons?: DialogButton[];
  small?: boolean;
}

/** A dialog that renders its own frame, for dialogs whose body or footer change while open. */
export interface CustomDialog {
  render: (close: () => void) => ReactNode;
}

export type DialogEntry = { id: number } & (DialogSpec | CustomDialog);

interface FrameProps {
  title: string;
  sub?: string;
  small?: boolean;
  /** The large list dialog (`.dlg.lg`). */
  large?: boolean;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
  backRef?: RefObject<HTMLDivElement | null>;
}

/** The `.dlg-back > .dlg` frame; focuses the first input, select or button 30 ms after opening. */
export function DialogFrame({ title, sub, small, large, onClose, children, footer, backRef }: FrameProps) {
  const own = useRef<HTMLDivElement>(null);
  const back = backRef || own;
  const titleId = useId();
  const close = useRef(onClose);
  close.current = onClose;
  useFocusReturn(true, back);
  useEffect(() => {
    const t = setTimeout(() => {
      const f = back.current?.querySelector<HTMLElement>('input,select,button.btn');
      f?.focus();
    }, 30);
    return () => clearTimeout(t);
  }, [back]);
  // Escape with the focus outside every dialog closes the top one.
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const el = back.current;
      if (e.key !== 'Escape' || !el) return;
      const all = document.querySelectorAll('.dlg-back');
      const active = document.activeElement;
      if (all[all.length - 1] !== el || (active && active.closest('.dlg-back'))) return;
      close.current();
    };
    addEventListener('keydown', onKey);
    return () => removeEventListener('keydown', onKey);
  }, [back]);
  return (
    <div
      className="dlg-back"
      ref={back}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={(e: KeyboardEvent<HTMLDivElement>) => {
        if (e.key === 'Escape') {
          e.stopPropagation();
          onClose();
          return;
        }
        if (trapTab(e, back.current?.querySelector('.dlg') ?? null)) e.stopPropagation();
      }}
    >
      <div className={`dlg${small ? ' sm' : ''}${large ? ' lg' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <div className="dh">
          <b id={titleId}>{title}</b>
          {sub ? <span>{sub}</span> : null}
          <button className="x" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="db">{children}</div>
        <div className="df">{footer}</div>
      </div>
    </div>
  );
}

function StandardDialog({ spec, close }: { spec: DialogSpec; close: () => void }) {
  const back = useRef<HTMLDivElement>(null);
  return (
    <DialogFrame
      title={spec.title}
      sub={spec.sub}
      small={spec.small}
      onClose={close}
      backRef={back}
      footer={(spec.buttons || []).map((b, i) => (
        <FooterButton key={i} index={i} button={b} back={back} close={close} />
      ))}
    >
      {spec.body}
    </DialogFrame>
  );
}

/**
 * A footer button: closes the dialog after its click, or after the click's promise settles. While
 * it waits it is disabled, so if it held the focus the dialog frame takes it, and Escape still
 * reaches the dialog.
 */
function FooterButton({ index, button: b, back, close }: { index: number; button: DialogButton; back: RefObject<HTMLDivElement | null>; close: () => void }) {
  const { shown, run } = useBusyAction();
  const self = useRef<HTMLButtonElement>(null);
  const after = (r: boolean | void) => {
    if (r !== false && !b.keep) close();
  };
  useLayoutEffect(() => {
    if (!shown) return;
    const active = document.activeElement;
    if (!active || active === self.current || active === document.body) back.current?.querySelector<HTMLElement>('.dlg')?.focus();
  }, [shown, back]);
  return (
    <button
      ref={self}
      className={`btn ${b.cls || ''}`}
      data-i={index}
      disabled={shown}
      aria-busy={shown ? 'true' : undefined}
      onClick={() =>
        run(() => {
          const r = b.onClick && back.current ? b.onClick(back.current, close) : undefined;
          if (r instanceof Promise) return r.then(after);
          after(r);
        })
      }
    >
      {shown ? <span className="spin"></span> : null}
      {b.label}
    </button>
  );
}

export function Dialog() {
  const st = useStore();
  return (
    <>
      {st.ui.dialogs.map((d) => {
        const close = () => st.closeDialog(d.id);
        return 'render' in d ? (
          <Fragment key={d.id}>{d.render(close)}</Fragment>
        ) : (
          <StandardDialog key={d.id} spec={d} close={close} />
        );
      })}
    </>
  );
}
