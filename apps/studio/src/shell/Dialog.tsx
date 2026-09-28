/**
 * Modal dialogs: title, sub, body, footer buttons, closed with ×, the backdrop or Escape.
 * Markup and behaviour from reference/ontaix-studio-reference.html lines 916-919 (`dialog`).
 * Dialogs stack: one opened from another sits on top of it, as appended elements do in the
 * reference.
 */
import { useEffect, useRef, type ReactNode, type RefObject } from 'react';

import { useStore } from './dom';

export interface DialogButton {
  label: string;
  cls?: string;
  /** Returns false to keep the dialog open. */
  onClick?: (root: HTMLDivElement, close: () => void) => boolean | void;
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
        <button
          key={i}
          className={`btn ${b.cls || ''}`}
          data-i={i}
          onClick={() => {
            const r = b.onClick && back.current ? b.onClick(back.current, close) : undefined;
            if (r !== false && !b.keep) close();
          }}
        >
          {b.label}
        </button>
      ))}
    >
      {spec.body}
    </DialogFrame>
  );
}

export function Dialog() {
  const st = useStore();
  return (
    <>
      {st.ui.dialogs.map((d) => {
        const close = () => st.closeDialog(d.id);
        return 'render' in d ? (
          <DialogSlot key={d.id}>{d.render(close)}</DialogSlot>
        ) : (
          <StandardDialog key={d.id} spec={d} close={close} />
        );
      })}
    </>
  );
}

function DialogSlot({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
