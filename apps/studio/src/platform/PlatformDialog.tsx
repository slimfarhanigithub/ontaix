/**
 * A platform dialog in the reference's `dialog()` frame: a form of fields, a note under them,
 * and one action button. Enter submits. A refusal keeps the dialog open and puts the Problem's
 * `detail` in the `.msg` in place of the note; success closes it.
 */
import { useState, type ReactNode } from 'react';

import { ApiError } from '../api/types';
import { FormMessage } from '../auth/AuthPage';
import { useBusyAction } from '../shell/busy';
import { DialogFrame } from '../shell/Dialog';

interface Props {
  title: string;
  sub?: string;
  small?: boolean;
  close: () => void;
  /** The action button's label. */
  label: string;
  /** The note under the fields, shown until a refusal replaces it. */
  note?: string;
  /** The call the button makes; a rejection with an API problem is shown, anything else logged. */
  onSave: () => Promise<unknown>;
  /** Runs after a refusal, for example to clear a password field. */
  onRefused?: () => void;
  children: ReactNode;
}

export function PlatformDialog({ title, sub, small, close, label, note, onSave, onRefused, children }: Props) {
  const [error, setError] = useState('');
  const { shown, run } = useBusyAction();
  const save = () =>
    void run(() =>
      onSave().then(
        () => close(),
        (err: unknown) => {
          onRefused?.();
          if (err instanceof ApiError) setError(err.problem.detail || err.problem.title);
          else console.error('platform call failed', err);
        },
      ),
    );
  return (
    <DialogFrame
      title={title}
      sub={sub}
      small={small}
      onClose={close}
      footer={
        <button className="btn primary" data-i="0" disabled={shown} aria-busy={shown ? 'true' : undefined} onClick={save}>
          {shown ? <span className="spin"></span> : null}
          {label}
        </button>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <div className="form">
          {children}
          {error || note ? <FormMessage text={error || note || ''} error={!!error} /> : null}
        </div>
      </form>
    </DialogFrame>
  );
}
