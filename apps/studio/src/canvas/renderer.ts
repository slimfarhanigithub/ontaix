/**
 * The frame loop and the pointer interactions of the canvas. Ported from
 * reference/ontaix-studio-reference.html lines 241-242 (`resize` wiring), 467-474 (`frame`,
 * `frameBody`), 477 and 493-504 (hover, drag, pan, zoom). The ghost drag path is not part of
 * the port.
 */
import { now } from '../runtime/clock';
import { drawCell } from './cells';
import { focusOnCell, focusOnDomain, hit, hitAt, hitChip } from './focus';
import { hitDomain } from './hulls';
import { drawLinks } from './links';
import { drawNeck } from './neck';
import { step } from './physics';
import { background, drawCompanies, drawDomains } from './regions';
import { neighbours, shown, type SceneState } from './state';
import { themeFor } from './themes';
import type { Company, Link, Node, SplitInfo } from './types';
import { createView, resize, toWorld, worldTransform, type View } from './view';

/** Shell reactions to canvas gestures. */
export interface RendererHooks {
  openDrawer(n: Node): void;
  closeDrawer(): void;
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
  applyTheme(name: string): void;
  clamp(v: number, a: number, b: number): number;
}

const clampN = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

export function createRenderer(canvas: HTMLCanvasElement, s: SceneState, hooks: RendererHooks): Renderer {
  const v = createView(canvas);
  let last = now();
  let frameErrors = 0;
  let domCountShown = -1;
  let raf = 0;
  let moved = 0;
  let dragStart: { x: number; y: number } | null = null;
  let clickedRoot: Node | null = null;

  function frameBody(): void {
    const t = now(),
      dt = Math.min(0.05, t - last);
    last = t;
    if (canvas.width < 2 || canvas.height < 2) {
      resize(v);
      return;
    }
    step(s, v, dt);
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
    drawCompanies(s, v, t);
    drawDomains(s, v, t);
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
    if (s.dragging) {
      const [wx, wy] = toWorld(v, s.cam, e.clientX, e.clientY);
      s.dragging.x = wx;
      s.dragging.y = wy;
      s.dragging.vx = s.dragging.vy = 0;
      moved++;
      const tgt = hitAt(s, wx, wy, s.dragging);
      s.dropTarget = tgt;
      s.hover = tgt || s.dragging;
      s.focusSet = tgt ? new Set([tgt, s.dragging]) : neighbours(s, s.dragging);
      return;
    }
    if (s.panning) {
      s.userZoomed = true;
      s.cam.tx -= e.movementX / s.cam.s;
      s.cam.ty -= e.movementY / s.cam.s;
      s.cam.x = s.cam.tx;
      s.cam.y = s.cam.ty;
      moved++;
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
    moved = 0;
    const n = hit(s, v, e.clientX, e.clientY);
    if (n) hooks.setActive(n.company);
    clickedRoot = n && n.fixed ? n : null;
    if (n && !n.fixed) {
      s.dragging = n;
      n.drag = true;
      dragStart = { x: n.x, y: n.y };
      s.dropTarget = null;
      canvas.classList.add('drag');
    } else if (!n) {
      s.panning = true;
      canvas.classList.add('drag');
    }
  };

  const onPointerUp = (e: PointerEvent) => {
    canvas.classList.remove('drag');
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
          hooks.closeNewBox();
          hooks.closeLinkBox();
          hooks.closeDrawer();
        }
      }
    }
    if (s.dragging && moved <= 3 && !s.dropTarget) {
      if (!s.lineageNode) focusOnCell(s, s.dragging);
      hooks.openDrawer(s.dragging);
    }
    if (clickedRoot && moved <= 3) {
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
    s.cam.ts = clampN(s.cam.ts * (1 - e.deltaY * 0.0012), 0.3, 2.4);
  };

  const onPointerLeave = () => {
    s.hover = null;
    s.focusSet = s.stickyFocus;
  };

  return {
    v,
    clamp: clampN,
    start() {
      addEventListener('resize', onResize);
      document.addEventListener('fullscreenchange', onFullscreen);
      canvas.addEventListener('pointermove', onPointerMove);
      canvas.addEventListener('pointerdown', onPointerDown);
      canvas.addEventListener('pointerup', onPointerUp);
      canvas.addEventListener('dblclick', onDblClick);
      canvas.addEventListener('wheel', onWheel, { passive: false });
      canvas.addEventListener('pointerleave', onPointerLeave);
      resize(v);
      last = now();
      frame();
    },
    stop() {
      cancelAnimationFrame(raf);
      removeEventListener('resize', onResize);
      document.removeEventListener('fullscreenchange', onFullscreen);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointerup', onPointerUp);
      canvas.removeEventListener('dblclick', onDblClick);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('pointerleave', onPointerLeave);
    },
    applyTheme(name) {
      v.TH = themeFor(name);
      document.documentElement.setAttribute('data-theme', name === 'light' ? 'light' : 'dark');
    },
  };
}
