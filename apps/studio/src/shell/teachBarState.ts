/**
 * Whether the teach bar is open, remembered per browser. Storage can be missing or refuse access
 * (private windows, blocked site data), so every read and write is guarded and the bar starts
 * collapsed when nothing can be read.
 */

/** The localStorage key holding `1` while the teach bar is open. */
export const EXPANDED_KEY = 'ontaix.teachBar.expanded';

export function readExpanded(): boolean {
  try {
    return localStorage.getItem(EXPANDED_KEY) === '1';
  } catch {
    return false;
  }
}

export function writeExpanded(expanded: boolean): void {
  try {
    localStorage.setItem(EXPANDED_KEY, expanded ? '1' : '0');
  } catch {
    // Nothing is remembered; the bar still opens and closes.
  }
}
