/**
 * The frame of the sign-in and "Choose a new password" pages: the page background with no
 * canvas, the reference's wordmark centred above a `.dlg.sm` card without an × button, since
 * neither page can be closed. The card is a form, so Enter submits it.
 */
import type { FormEvent, ReactNode } from 'react';

import { refStyle } from '../shell/dom';

interface Props {
  title: string;
  sub: string;
  onSubmit: () => void;
  children: ReactNode;
  footer: ReactNode;
}

export function AuthPage({ title, sub, onSubmit, children, footer }: Props) {
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    onSubmit();
  };
  return (
    <div
      className="signin"
      ref={refStyle('position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:28px;padding:20px;background:var(--bg)')}
    >
      <div className="wordmark">
        <i></i>Ontaix <small>business as a product</small>
      </div>
      <form className="dlg sm" aria-labelledby="authTitle" onSubmit={submit} noValidate>
        <div className="dh">
          <b id="authTitle" style={{ whiteSpace: 'nowrap' }}>
            {title}
          </b>
          <span>{sub}</span>
        </div>
        <div className="db">{children}</div>
        <div className="df">{footer}</div>
      </form>
    </div>
  );
}

/** The `.msg` line under a form: the note, or the error in the conflict colour. */
export function FormMessage({ text, error }: { text: string; error?: boolean }) {
  return (
    <div className="full msg" role={error ? 'alert' : undefined} style={error ? { color: 'var(--conflict)' } : undefined}>
      {text}
    </div>
  );
}
