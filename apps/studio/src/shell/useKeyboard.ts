/**
 * Keyboard shortcuts: the two `keydown` listeners of reference/ontaix-studio-reference.html
 * lines 887 and 1069, without the Space, ArrowRight and R shortcuts. A letter does nothing while
 * the focus is in a text field, a select, a text area or editable content, while Ctrl, Alt or
 * Meta is held, or while a dialog is open; with the admin portal open only G (close it) works.
 * Escape is left to an open dialog, which closes itself.
 */
import { useEffect } from 'react';

import { store } from '../store/store';

/** True when the key goes to a field the user is typing in. */
export function isEditable(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || !el.tagName) return false;
  return el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA' || el.isContentEditable;
}

/** True when a letter key must not act as a shortcut. */
function letterBlocked(e: KeyboardEvent): boolean {
  return e.ctrlKey || e.altKey || e.metaKey || isEditable(e.target) || store.ui.dialogs.length > 0;
}

export function useKeyboard(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (!store.ui.dialogs.length) store.escape();
        return;
      }
      if (letterBlocked(e) || store.ui.adminOpen) return;
      if (e.key === 'a' || e.key === 'A') store.arrange();
      if (e.key === 'i' || e.key === 'I') (document.getElementById('importFile') as HTMLInputElement | null)?.click();
      if (e.key === 'l' || e.key === 'L') store.toggleLegend();
      if (e.key === 'd' || e.key === 'D') store.toggleDomainsCard();
      if (e.key === 'p' || e.key === 'P') store.togglePanel();
      if (e.key === 's' || e.key === 'S') store.toggleSkip();
      if (e.key === 'c' || e.key === 'C') store.toggleCoverage();
      if (e.key === 'f' || e.key === 'F') {
        if (document.fullscreenElement) void document.exitFullscreen();
        else void document.documentElement.requestFullscreen?.();
      }
    };
    const onAdminKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (store.ui.adminOpen && !store.ui.dialogs.length && !isEditable(e.target)) store.closeAdmin();
        return;
      }
      if (letterBlocked(e)) return;
      if (e.key === 'g' || e.key === 'G') {
        if (store.ui.adminOpen) store.closeAdmin();
        else store.openAdmin();
      }
    };
    addEventListener('keydown', onKey);
    addEventListener('keydown', onAdminKey);
    return () => {
      removeEventListener('keydown', onKey);
      removeEventListener('keydown', onAdminKey);
    };
  }, []);
}
