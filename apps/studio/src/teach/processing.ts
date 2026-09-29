/**
 * The count of teach bar parses in flight, which the caption shows as Processing.
 */
import { store } from '../store/store';

/**
 * Counts one teach bar parse as pending, for the caption's Processing line; the returned function
 * ends it and does nothing when called again.
 */
export function beginProcessing(): () => void {
  store.ui.processing++;
  store.bump();
  let ended = false;
  return () => {
    if (ended) return;
    ended = true;
    store.ui.processing--;
    store.bump();
  };
}
