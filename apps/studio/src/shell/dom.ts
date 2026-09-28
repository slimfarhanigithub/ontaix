/**
 * Small DOM helpers for components that reproduce the reference markup.
 */
import { useSyncExternalStore } from 'react';

import { store } from '../store/store';

/** Re-renders the caller on every store change and hands back the store. */
export function useStore(): typeof store {
  useSyncExternalStore(store.subscribe, store.getVersion, store.getVersion);
  return store;
}

/**
 * A ref callback that writes an inline `style` attribute verbatim. The reference relies on the
 * declaration order inside some inline styles (`margin-left:auto; all:unset; ...`), which a
 * style object cannot promise to keep.
 */
export const refStyle =
  (css: string) =>
  (el: Element | null): void => {
    if (el) el.setAttribute('style', css);
  };

/** Capitalises the first letter, the reference's `title`. */
export const titleCase = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);
