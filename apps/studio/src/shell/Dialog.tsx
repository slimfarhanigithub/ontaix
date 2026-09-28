/**
 * Modal dialog: title, sub, body, footer buttons, closed with ×, the backdrop or Escape.
 * Markup and behaviour from reference/ontaix-studio-reference.html lines 916-919 (`dialog`).
 */
import { useEffect, useRef, type ReactNode } from 'react';

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

export function Dialog() {
  const st = useStore();
  const spec = st.ui.dialog;
  const back = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!spec) return;
    const t = setTimeout(() => {
      const f = back.current?.querySelector<HTMLElement>('input,select,button.btn');
      f?.focus();
    }, 30);
    return () => clearTimeout(t);
  }, [spec]);

  if (!spec) return null;
  const close = () => st.closeDialog();
  return (
    <div
      className="dlg-back"
      ref={back}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation();
          close();
        }
      }}
    >
      <div className={`dlg${spec.small ? ' sm' : ''}`} role="dialog" aria-modal="true">
        <div className="dh">
          <b>{spec.title}</b>
          {spec.sub ? <span>{spec.sub}</span> : null}
          <button className="x" aria-label="Close" onClick={close}>
            ×
          </button>
        </div>
        <div className="db">{spec.body}</div>
        <div className="df">
          {(spec.buttons || []).map((b, i) => (
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
        </div>
      </div>
    </div>
  );
}
