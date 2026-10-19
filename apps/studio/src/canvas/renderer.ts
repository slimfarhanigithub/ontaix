/**
 * The frame loop and the pointer interactions of the canvas. Ported from
 * reference/ontaix-studio-reference.html lines 241-242 (`resize` wiring), 467-474 (`frame`,
 * `frameBody`), 477 and 493-504 (hover, drag, pan, zoom). The ghost drag path is not part of
 * the port. Two fingers on a touch screen pinch to zoom, as the wheel does; a second finger
 * cancels the drag or pan the first one started, and a pinch never counts as a click. A finger
 * held still on a cell for LONG_PRESS_MS selects it, as Shift+click does with a mouse.
 */
import { now } from '../runtime/clock';
import { BRAIN_MIN_ZOOM, brainStep } from '../demo/brainDemo';
import { drawBrain, drawBrainTint } from '../demo/brainLayer';
import { drawCell } from './cells';
import { focusOnCell, focusOnDomain, hit, hitAt, hitChip } from './focus';
import { hitDomain } from './hulls';
import { drawLinks } from './links';
import { drawNeck } from './neck';
import { step } from './physics';
import { background, drawCompanies, drawDomains } from './regions';
import { neighbours, shown, type SceneState } from './state';
import type { Company, Link, Node, SplitInfo } from './types';
import { createView, resize, toWorld, worldTransform, type View } from './view';

/** Shell reactions to canvas gestures. */
export interface RendererHooks {
  openDrawer(n: Node): void;
  closeDrawer(): void;
  /** Shift+click or Ctrl+click on a cell: adds it to the selection or takes it out. */
  toggleSelected(n: Node): void;
  clearSelection(): void;
  openLinkBox(a: Node, b: Node, sx: number, sy: number, link?: Link | null): void;
  closeNewBox(): void;
  closeLinkBox(): void;
  setActive(c: Company | null): void;
  caption(kicker: string, text: string): void;
}

export interface Renderer {
  v: View;
  start(): void;
  stop(): void;
}

const clampN = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

/** How far the wheel and a pinch zoom out: 0.3, or further while the demo brain is on. */
const minZoom = (s: SceneState): number => (s.brain ? BRAIN_MIN_ZOOM : 0.3);

/** A move count far above the 3 moves that end a click: set after a pinch or a cancelled pointer, so neither acts as one. */
const PINCHED = 1000;

/** How far a finger may wander, in CSS pixels, before its moves count: a tap jitters, a mouse click does not. */
const TOUCH_SLOP = 8;

/** How long a finger rests on a cell, without moving, before it selects the cell. */
const LONG_PRESS_MS = 500;

export function createRenderer(canvas: HTMLCanvasElement, s: SceneState, hooks: RendererHooks): Renderer {
  const v = createView(canvas);
  let last = now();
  let frameErrors = 0;
  let domCountShown = -1;
  let raf = 0;
  let moved = 0;
  let dragStart: { x: number; y: number } | null = null;
  let clickedRoot: Node | null = null;
  /** The cell under a Shift+click or Ctrl+click; it neither drags nor opens the drawer. */
  let modClick: Node | null = null;
  /** The pointers pressed on the canvas, by id, at their last position. */
  const pointers = new Map<number, { x: number; y: number }>();
  /** A two-finger pinch: the fingers' distance and the camera zoom when it started. */
  let pinch: { d: number; ts: number } | null = null;
  /** Where the press began, and whether its moves count yet (at once for a mouse or pen, past TOUCH_SLOP for a finger). */
  let downAt = { x: 0, y: 0 };
  let counting = true;
  const countMove = (e: PointerEvent) => {
    if (!counting && Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) >= TOUCH_SLOP) counting = true;
    if (counting) moved++;
  };
  /** The pending long press of a finger resting on a cell. */
  let press = 0;
  const cancelPress = () => {
    clearTimeout(press);
    press = 0;
  };

  const spread = (): number => {
    const [a, b] = [...pointers.values()];
    return Math.hypot(a.x - b.x, a.y - b.y) || 1;
  };

  function frameBody(): void {
    const t = now(),
      dt = Math.min(0.05, t - last);
    last = t;
    if (canvas.width < 2 || canvas.height < 2) {
      resize(v);
      return;
    }
    step(s, v, dt);
    brainStep(s, v, t);
    s.splitting = new Map<Node, SplitInfo>();
    for (const n of s.nodes)
      if (n.split) {
        const sp: SplitInfo = { p: clampN((t - n.split.start) / n.split.dur, 0, 1), ang: n.split.ang, broken: n.split.broken };
        s.splitting.set(n.split.from, sp);
        n.split.p = sp.p;
      }
    const total = s.nodes.length;
    if (total !== domCountShown) {
      domCountShown = total;
      s.effects.domainsChanged();
      if (s.domainFocus) focusOnDomain(s, s.domainFocus);
    }
    background(v);
    worldTransform(v, s.cam);
    if (s.brain) {
      // The demo's lobes stand in for the company and domain regions.
      drawBrainTint(s, v, t);
      drawBrain(s, v, t);
    } else {
      drawCompanies(s, v, t);
      drawDomains(s, v, t);
    }
    drawLinks(s, v, t);
    for (const n of s.nodes) if (n.split && shown(n)) drawNeck(s, v, n, t);
    const sorted = s.nodes
      .slice()
      .sort(
        (a, b) =>
          Number(a === s.hover) - Number(b === s.hover) ||
          (b.split && !b.split.broken ? 1 : 0) - (a.split && !a.split.broken ? 1 : 0),
      );
    for (const n of sorted) if (shown(n)) drawCell(s, v, n, t);
  }

  function frame(): void {
    raf = requestAnimationFrame(frame);
    try {
      frameBody();
    } catch (err) {
      if (frameErrors++ < 3) console.error('frame error', err);
    }
  }

  const onResize = () => resize(v);
  const onFullscreen = () => {
    setTimeout(onResize, 0);
    setTimeout(onResize, 120);
  };

  const onPointerMove = (e: PointerEvent) => {
    s.lastInteract = now();
    const prev = pointers.get(e.pointerId);
    if (prev) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch) {
      if (pointers.size >= 2) {
        s.userZoomed = true;
        s.cam.ts = clampN((pinch.ts * spread()) / pinch.d, minZoom(s), 2.4);
      }
      return;
    }
    if (s.dragging) {
      const [wx, wy] = toWorld(v, s.cam, e.clientX, e.clientY);
      s.dragging.x = wx;
      s.dragging.y = wy;
      s.dragging.vx = s.dragging.vy = 0;
      countMove(e);
      if (moved > 3) cancelPress();
      const tgt = hitAt(s, wx, wy, s.dragging);
      s.dropTarget = tgt;
      s.hover = tgt || s.dragging;
      s.focusSet = tgt ? new Set([tgt, s.dragging]) : neighbours(s, s.dragging);
      return;
    }
    if (s.panning) {
      s.userZoomed = true;
      const dx = prev ? e.clientX - prev.x : 0,
        dy = prev ? e.clientY - prev.y : 0;
      s.cam.tx -= dx / s.cam.s;
      s.cam.ty -= dy / s.cam.s;
      s.cam.x = s.cam.tx;
      s.cam.y = s.cam.ty;
      countMove(e);
      return;
    }
    const n = hit(s, v, e.clientX, e.clientY);
    if (n !== s.hover) {
      s.hover = n;
      s.focusSet = n ? neighbours(s, n) : s.stickyFocus;
    }
    canvas.classList.toggle('hover', !!n || !!hitChip(s, v, e.clientX, e.clientY));
  };

  const onPointerDown = (e: PointerEvent) => {
    s.lastInteract = now();
    canvas.setPointerCapture(e.pointerId);
    // The first pointer of a gesture starts afresh, so a lost release never leaves a stale finger behind.
    if (e.isPrimary) pointers.clear();
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size >= 2) {
      cancelPress();
      if (pointers.size === 2) startPinch();
      return;
    }
    moved = 0;
    downAt = { x: e.clientX, y: e.clientY };
    counting = e.pointerType !== 'touch';
    const n = hit(s, v, e.clientX, e.clientY);
    if (n) hooks.setActive(n.company);
    if (n && !n.fixed && (e.shiftKey || e.ctrlKey || e.metaKey)) {
      modClick = n;
      return;
    }
    clickedRoot = n && n.fixed ? n : null;
    if (n && !n.fixed) {
      s.dragging = n;
      n.drag = true;
      dragStart = { x: n.x, y: n.y };
      s.dropTarget = null;
      canvas.classList.add('drag');
      if (e.pointerType === 'touch') press = window.setTimeout(() => longPress(n), LONG_PRESS_MS);
    } else if (!n) {
      s.panning = true;
      canvas.classList.add('drag');
    }
  };

  /** A second finger: whatever the first one started stops, and the camera zooms with the fingers. */
  const startPinch = () => {
    if (s.dragging) {
      s.dragging.drag = false;
      if (dragStart) {
        s.dragging.x = dragStart.x;
        s.dragging.y = dragStart.y;
      }
    }
    s.dragging = null;
    s.dropTarget = null;
    s.panning = false;
    modClick = null;
    clickedRoot = null;
    moved = PINCHED;
    canvas.classList.remove('drag');
    pinch = { d: spread(), ts: s.cam.ts };
  };

  /** The finger rested on the cell: the cell goes back where it was and joins the selection or leaves it. */
  const longPress = (n: Node) => {
    press = 0;
    if (s.dragging !== n || moved > 3) return;
    n.drag = false;
    if (dragStart) {
      n.x = dragStart.x;
      n.y = dragStart.y;
    }
    s.dragging = null;
    s.dropTarget = null;
    moved = PINCHED;
    canvas.classList.remove('drag');
    hooks.toggleSelected(n);
    s.hover = null;
    s.focusSet = s.stickyFocus;
  };

  const onPointerUp = (e: PointerEvent) => {
    cancelPress();
    pointers.delete(e.pointerId);
    if (pinch) {
      // A third finger lifted: the two left measure from here on.
      pinch = pointers.size >= 2 ? { d: spread(), ts: s.cam.ts } : null;
      return;
    }
    canvas.classList.remove('drag');
    if (modClick) {
      if (moved <= 3) hooks.toggleSelected(modClick);
      modClick = null;
      s.hover = null;
      s.focusSet = s.stickyFocus;
      return;
    }
    if (!s.dragging && !clickedRoot && moved <= 3) {
      const l = hitChip(s, v, e.clientX, e.clientY);
      if (l) hooks.openLinkBox(l.a, l.b, e.clientX, e.clientY, l);
      else {
        const d = hitDomain(s, v, e.clientX, e.clientY);
        if (d && d !== s.domainFocus) {
          s.cellFocus = null;
          focusOnDomain(s, d);
          hooks.caption(
            d.name,
            `${d.name} and the concepts of other domain products it relates to. Click elsewhere to release.`,
          );
        } else {
          s.cellFocus = null;
          focusOnDomain(s, null);
          hooks.clearSelection();
          hooks.closeNewBox();
          hooks.closeLinkBox();
          hooks.closeDrawer();
        }
      }
    }
    if (s.dragging && moved <= 3 && !s.dropTarget) {
      hooks.clearSelection();
      if (!s.lineageNode) focusOnCell(s, s.dragging);
      hooks.openDrawer(s.dragging);
    }
    if (clickedRoot && moved <= 3) {
      hooks.clearSelection();
      if (!s.lineageNode) focusOnCell(s, clickedRoot);
      hooks.openDrawer(clickedRoot);
      clickedRoot = null;
    }
    if (s.dragging) {
      s.dragging.drag = false;
      if (s.dropTarget && moved > 3 && dragStart) {
        const a = s.dragging,
          b = s.dropTarget;
        a.tween = { fx: a.x, fy: a.y, tx: dragStart.x, ty: dragStart.y, start: now(), pin: a.pinned };
        hooks.openLinkBox(a, b, e.clientX, e.clientY);
      }
    }
    s.dragging = null;
    s.dropTarget = null;
    s.panning = false;
    s.hover = null;
    s.focusSet = s.stickyFocus;
  };

  const onDblClick = (e: MouseEvent) => {
    const n = hit(s, v, e.clientX, e.clientY);
    if (n) {
      s.userZoomed = true;
      s.cam.tx = n.x;
      s.cam.ty = n.y;
      s.cam.ts = 1.6;
    } else {
      s.userZoomed = false;
    }
  };

  const onWheel = (e: WheelEvent) => {
    e.preventDefault();
    s.lastInteract = now();
    s.userZoomed = true;
    s.cam.ts = clampN(s.cam.ts * (1 - e.deltaY * 0.0012), minZoom(s), 2.4);
  };

  /** The browser took the pointer back (a system gesture): nothing it started counts as a click. */
  const onPointerCancel = (e: PointerEvent) => {
    moved = PINCHED;
    s.dropTarget = null;
    onPointerUp(e);
  };

  /** A finger held on the canvas selects a cell; the browser's own long-press menu would cover it. */
  const onContextMenu = (e: Event) => e.preventDefault();

  const onPointerLeave = () => {
    s.hover = null;
    s.focusSet = s.stickyFocus;
  };

  return {
    v,
    start() {
      addEventListener('resize', onResize);
      document.addEventListener('fullscreenchange', onFullscreen);
      canvas.addEventListener('pointermove', onPointerMove);
      canvas.addEventListener('pointerdown', onPointerDown);
      canvas.addEventListener('pointerup', onPointerUp);
      canvas.addEventListener('pointercancel', onPointerCancel);
      canvas.addEventListener('contextmenu', onContextMenu);
      canvas.addEventListener('dblclick', onDblClick);
      canvas.addEventListener('wheel', onWheel, { passive: false });
      canvas.addEventListener('pointerleave', onPointerLeave);
      resize(v);
      last = now();
      frame();
    },
    stop() {
      cancelAnimationFrame(raf);
      cancelPress();
      removeEventListener('resize', onResize);
      document.removeEventListener('fullscreenchange', onFullscreen);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointerup', onPointerUp);
      canvas.removeEventListener('pointercancel', onPointerCancel);
      canvas.removeEventListener('contextmenu', onContextMenu);
      canvas.removeEventListener('dblclick', onDblClick);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('pointerleave', onPointerLeave);
    },
  };
}
