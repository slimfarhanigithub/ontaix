/**
 * The canvas element and the renderer bound to it.
 */
import { useEffect, useRef } from 'react';

import { createRenderer } from '../canvas/renderer';
import { useT } from '../i18n/i18n';
import { store } from '../store/store';

export function CanvasView() {
  const t = useT();
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const renderer = createRenderer(canvas, store.s, {
      openDrawer: (n) => store.openDrawer(n),
      closeDrawer: () => store.closeDrawer(),
      toggleSelected: (n) => store.toggleSelected(n),
      clearSelection: () => store.clearSelection(),
      openLinkBox: (a, b, sx, sy, link) => store.openLinkBox(a, b, sx, sy, link ?? null),
      closeNewBox: () => store.closeNewBox(),
      closeLinkBox: () => store.closeLinkBox(),
      setActive: (c) => store.setActive(c),
      caption: (k, t) => store.caption(k, t),
    });
    store.attachRenderer(renderer);
    renderer.start();
    return () => renderer.stop();
  }, []);
  return <canvas id="brain" aria-label={t('shell.canvas.label')} ref={ref}></canvas>;
}
