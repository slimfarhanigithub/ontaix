/**
 * Modal dialogs: title, sub, body, footer buttons, closed with ×, the backdrop or Escape.
 * Markup and behaviour from reference/ontaix-studio-reference.html lines 916-919 (`dialog`).
 * Dialogs stack: one opened from another sits on top of it, as appended elements do in the
 * reference.
 */
import { Fragment, useEffect, useRef, type ReactNode, type RefObject } from 'react';

import { useBusyAction } from './busy';
import { useStore } from './dom';

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
  useEffect(() => {
    const t = setTimeout(() => {
      const f = back.current?.querySelector<HTMLElement>('input,select,button.btn');
      f?.focus();
    }, 30);
    return () => clearTimeout(t);
  }, [back]);
  return (
    <div
      className="dlg-back"
      ref={back}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation();
          onClose();
        }
      }}
    >
      <div className={`dlg${small ? ' sm' : ''}${large ? ' lg' : ''}`} role="dialog" aria-modal="true">
        <div className="dh">
          <b>{title}</b>
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

/** A footer button: closes the dialog after its click, or after the click's promise settles. */
function FooterButton({ index, button: b, back, close }: { index: number; button: DialogButton; back: RefObject<HTMLDivElement | null>; close: () => void }) {
  const { shown, run } = useBusyAction();
  const after = (r: boolean | void) => {
    if (r !== false && !b.keep) close();
  };
  return (
    <button
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
