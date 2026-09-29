/**
 * The waiting state of a click that awaits the API. While the click's promise is pending, a
 * second click is ignored; once the wait passes BUSY_DELAY_MS the button is disabled, carries
 * `aria-busy="true"` and shows the reference's `.spin` ring before its unchanged label. Faster
 * calls change nothing visible. The state clears when the promise settles, fulfilled or rejected.
 */
import { useCallback, useEffect, useRef, useState, type ButtonHTMLAttributes } from 'react';

/** How long a click waits before its button shows the spinner, in milliseconds. */
export const BUSY_DELAY_MS = 250;

/** True once `active` has stayed true for `ms`; false again as soon as it turns false. */
export function useDelayed(active: boolean, ms: number = BUSY_DELAY_MS): boolean {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!active) {
      setShown(false);
      return;
    }
    const t = setTimeout(() => setShown(true), ms);
    return () => clearTimeout(t);
  }, [active, ms]);
  return active && shown;
}

export interface BusyAction {
  /** True while the last action's promise is pending and the wait has passed BUSY_DELAY_MS. */
  shown: boolean;
  /**
   * Runs `action` unless one is pending; a returned promise keeps the action pending until it
   * settles, and the promise handed back settles with it. A synchronous action hands back undefined.
   */
  run: (action: () => unknown) => Promise<unknown> | undefined;
}

/** Tracks one awaited click at a time; a rejection clears the state and reaches the caller. */
export function useBusyAction(): BusyAction {
  const [pending, setPending] = useState(false);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const run = useCallback((action: () => unknown): Promise<unknown> | undefined => {
    if (inFlight.current) return undefined;
    const result = action();
    if (!isThenable(result)) return undefined;
    inFlight.current = true;
    setPending(true);
    const settle = () => {
      inFlight.current = false;
      if (mounted.current) setPending(false);
    };
    return Promise.resolve(result).finally(settle);
  }, []);
  return { shown: useDelayed(pending), run };
}

type BusyButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onClick'> & {
  /** The click; a returned promise makes the button wait for it. */
  onClick: () => unknown;
};

/** A `<button>` whose awaited click shows the waiting state. */
export function BusyButton({ onClick, disabled, children, ...rest }: BusyButtonProps) {
  const { shown, run } = useBusyAction();
  return (
    <button {...rest} disabled={disabled || shown} aria-busy={shown ? 'true' : undefined} onClick={() => void run(onClick)}>
      {shown ? <span className="spin"></span> : null}
      {children}
    </button>
  );
}

function isThenable(v: unknown): v is PromiseLike<unknown> {
  return !!v && typeof (v as PromiseLike<unknown>).then === 'function';
}
