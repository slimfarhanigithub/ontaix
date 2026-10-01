/**
 * The user's Skip animation choice, remembered per browser. Storage can be missing or refuse
 * access (private windows, blocked site data), so every read and write is guarded and animations
 * play when nothing can be read.
 */

/** The localStorage key holding `1` while the user skips animations. */
export const SKIP_ANIMATION_KEY = 'ontaix.skipAnimation';

export function readSkipAnimation(): boolean {
  try {
    return localStorage.getItem(SKIP_ANIMATION_KEY) === '1';
  } catch {
    return false;
  }
}

export function writeSkipAnimation(skip: boolean): void {
  try {
    localStorage.setItem(SKIP_ANIMATION_KEY, skip ? '1' : '0');
  } catch {
    // Nothing is remembered; the choice lasts for the session.
  }
}
