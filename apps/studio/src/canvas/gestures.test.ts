import { createRenderer, type RendererHooks } from './renderer';
import { createScene, type SceneState } from './state';
import { northwindModel, settleTweens } from './testModels';
import type { Node } from './types';
import { CX } from './view';

/** A pointer event with the fields the canvas reads; jsdom has no PointerEvent constructor. */
function pointer(type: string, x: number, y: number, id: number, pointerType: 'mouse' | 'touch', isPrimary = true): Event {
  return Object.assign(new MouseEvent(type, { clientX: x, clientY: y, bubbles: true }), { pointerId: id, pointerType, isPrimary });
}

function setup() {
  const ctx = new Proxy({} as CanvasRenderingContext2D, {
    get: (_t, prop) => (prop === 'canvas' ? {} : () => ({ addColorStop() {} })),
    set: () => true,
  });
  HTMLCanvasElement.prototype.getContext = (() => ctx) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.setPointerCapture = () => {};
  vi.stubGlobal('requestAnimationFrame', () => 0);
  vi.stubGlobal('cancelAnimationFrame', () => {});
  const s: SceneState = createScene();
  northwindModel(s);
  settleTweens(s);
  const hooks: RendererHooks = {
    openDrawer: vi.fn(),
    closeDrawer: vi.fn(),
    toggleSelected: vi.fn(),
    clearSelection: vi.fn(),
    openLinkBox: vi.fn(),
    closeNewBox: vi.fn(),
    closeLinkBox: vi.fn(),
    setActive: vi.fn(),
    caption: vi.fn(),
  };
  const canvas = document.createElement('canvas');
  const r = createRenderer(canvas, s, hooks);
  r.start();
  const cell = s.nodes.find((n) => !n.fixed && n.kind === 'concept') as Node;
  const at = (n: Node): [number, number] => [(n.x - s.cam.x) * s.cam.s + CX(r.v), (n.y - s.cam.y) * s.cam.s + r.v.H / 2];
  return { s, hooks, canvas, r, cell, at };
}

describe('canvas touch gestures', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('a tap that jitters less than 8 px still opens the drawer', () => {
    const { hooks, canvas, cell, at, r } = setup();
    const [x, y] = at(cell);
    canvas.dispatchEvent(pointer('pointerdown', x, y, 5, 'touch'));
    for (let i = 1; i <= 6; i++) canvas.dispatchEvent(pointer('pointermove', x + (i % 2) * 3, y + 2, 5, 'touch'));
    canvas.dispatchEvent(pointer('pointerup', x, y, 5, 'touch'));
    expect(hooks.openDrawer).toHaveBeenCalledWith(cell);
    r.stop();
  });

  it('a mouse that moves 4 times drags as it always has, without opening the drawer', () => {
    const { hooks, canvas, cell, at, r } = setup();
    const [x, y] = at(cell);
    canvas.dispatchEvent(pointer('pointerdown', x, y, 1, 'mouse'));
    for (let i = 1; i <= 4; i++) canvas.dispatchEvent(pointer('pointermove', x + i, y, 1, 'mouse'));
    canvas.dispatchEvent(pointer('pointerup', x + 4, y, 1, 'mouse'));
    expect(hooks.openDrawer).not.toHaveBeenCalled();
    r.stop();
  });

  it('two fingers spreading to twice their distance double the zoom and count as no click', () => {
    const { s, hooks, canvas, r } = setup();
    const ts = s.cam.ts;
    canvas.dispatchEvent(pointer('pointerdown', 100, 300, 7, 'touch'));
    canvas.dispatchEvent(pointer('pointerdown', 200, 300, 8, 'touch', false));
    canvas.dispatchEvent(pointer('pointermove', 50, 300, 7, 'touch'));
    canvas.dispatchEvent(pointer('pointermove', 250, 300, 8, 'touch', false));
    expect(s.cam.ts).toBeCloseTo(Math.min(2.4, ts * 2));
    canvas.dispatchEvent(pointer('pointerup', 50, 300, 7, 'touch'));
    canvas.dispatchEvent(pointer('pointerup', 250, 300, 8, 'touch', false));
    expect(hooks.openDrawer).not.toHaveBeenCalled();
    expect(hooks.closeDrawer).not.toHaveBeenCalled();
    r.stop();
  });

  it('a third finger lifting leaves the zoom where it is, then the two left pinch on', () => {
    const { s, canvas, r } = setup();
    canvas.dispatchEvent(pointer('pointerdown', 100, 300, 1, 'touch'));
    canvas.dispatchEvent(pointer('pointerdown', 200, 300, 2, 'touch', false));
    canvas.dispatchEvent(pointer('pointerdown', 400, 300, 3, 'touch', false));
    canvas.dispatchEvent(pointer('pointerup', 100, 300, 1, 'touch'));
    const ts = s.cam.ts;
    canvas.dispatchEvent(pointer('pointermove', 200, 300, 2, 'touch', false));
    expect(s.cam.ts).toBeCloseTo(ts);
    canvas.dispatchEvent(pointer('pointermove', 0, 300, 2, 'touch', false));
    expect(s.cam.ts).toBeCloseTo(Math.min(2.4, ts * 2));
    r.stop();
  });

  it('the canvas shows no context menu', () => {
    const { canvas, r } = setup();
    const e = new MouseEvent('contextmenu', { cancelable: true });
    canvas.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(true);
    r.stop();
  });

  it('a finger resting on a cell for 500 ms selects it, puts it back and opens no drawer', () => {
    vi.useFakeTimers();
    const { s, hooks, canvas, cell, at, r } = setup();
    const [x, y] = at(cell);
    const [cx, cy] = [cell.x, cell.y];
    canvas.dispatchEvent(pointer('pointerdown', x, y, 9, 'touch'));
    canvas.dispatchEvent(pointer('pointermove', x + 2, y + 2, 9, 'touch'));
    vi.advanceTimersByTime(500);
    expect(hooks.toggleSelected).toHaveBeenCalledWith(cell);
    expect([cell.x, cell.y]).toEqual([cx, cy]);
    expect(s.dragging).toBeNull();
    canvas.dispatchEvent(pointer('pointerup', x, y, 9, 'touch'));
    expect(hooks.openDrawer).not.toHaveBeenCalled();
    r.stop();
  });

  it('a mouse held still on a cell never selects it', () => {
    vi.useFakeTimers();
    const { hooks, canvas, cell, at, r } = setup();
    const [x, y] = at(cell);
    canvas.dispatchEvent(pointer('pointerdown', x, y, 1, 'mouse'));
    vi.advanceTimersByTime(1000);
    canvas.dispatchEvent(pointer('pointerup', x, y, 1, 'mouse'));
    expect(hooks.toggleSelected).not.toHaveBeenCalled();
    expect(hooks.openDrawer).toHaveBeenCalledWith(cell);
    r.stop();
  });
});
