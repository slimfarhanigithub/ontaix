/**
 * Keyboard shortcuts: the two `keydown` listeners of reference/ontaix-studio-reference.html
 * lines 887 and 1069, without the Space, ArrowRight and R shortcuts.
 */
import { useEffect } from 'react';

import { store } from '../store/store';

export function useKeyboard(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' && e.key !== 'Escape') return;
      if (e.key === 'a' || e.key === 'A') store.arrange();
      if (e.key === 'i' || e.key === 'I') (document.getElementById('importFile') as HTMLInputElement | null)?.click();
      if (e.key === 'l' || e.key === 'L') store.toggleLegend();
      if (e.key === 'd' || e.key === 'D') store.toggleDomainsCard();
      if (e.key === 'p' || e.key === 'P') store.togglePanel();
      if (e.key === 's' || e.key === 'S') store.toggleSkip();
      if (e.key === 'Escape') store.escape();
      if (e.key === 'c' || e.key === 'C') store.toggleCoverage();
      if (e.key === 'f' || e.key === 'F') {
        if (document.fullscreenElement) void document.exitFullscreen();
        else void document.documentElement.requestFullscreen?.();
      }
    };
    const onAdminKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'SELECT') return;
      if (e.key === 'g' || e.key === 'G') {
        if (store.ui.adminOpen) store.closeAdmin();
        else store.openAdmin();
      }
      if (e.key === 'Escape' && store.ui.adminOpen) store.closeAdmin();
    };
    addEventListener('keydown', onKey);
    addEventListener('keydown', onAdminKey);
    return () => {
      removeEventListener('keydown', onKey);
      removeEventListener('keydown', onAdminKey);
    };
  }, []);
}
