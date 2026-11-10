import { cellInView, drawCell } from './cells';
import { drawLinks } from './links';
import { createRenderer, type RendererHooks } from './renderer';
import { addLink, addNode, createScene, type SceneState } from './state';
import { northwindModel, settleTweens } from './testModels';
import type { View } from './view';

/** A 2D context that counts its calls; jsdom draws nothing. */
function countingContext(): { ctx: CanvasRenderingContext2D; calls: Map<string, number> } {
  const calls = new Map<string, number>();
  const ctx = new Proxy({} as CanvasRenderingContext2D, {
    get: (_t, prop) => {
      if (prop === 'canvas') return {};
      return (..._args: unknown[]) => {
        calls.set(String(prop), (calls.get(String(prop)) || 0) + 1);
        return { addColorStop() {} };
      };
    },
    set: () => true,
  });
  return { ctx, calls };
}

/** A view showing the world rectangle `world` at zoom `s`, for the draw functions. */
function viewOf(ctx: CanvasRenderingContext2D, world: [number, number, number, number]): View {
  return { ctx, W: 1440, H: 900, DPR: 1, world, TH: { INK: '0,0,0', INK2: '0,0,0', CHIP: '0,0,0', shadow: 'rgba(0,0,0,0)' }, panelOff: () => false } as unknown as View;
}

const hooks = (): RendererHooks => ({
  openDrawer: vi.fn(),
  closeDrawer: vi.fn(),
  toggleSelected: vi.fn(),
  clearSelection: vi.fn(),
  openLinkBox: vi.fn(),
  closeNewBox: vi.fn(),
  closeLinkBox: vi.fn(),
  setActive: vi.fn(),
  caption: vi.fn(),
});

/** Draws one frame of the model with the camera at `x` and zoom `zoom`, and returns the counted context calls. */
function frameAt(x: number, zoom: number): { s: SceneState; calls: Map<string, number> } {
  const { ctx, calls } = countingContext();
  HTMLCanvasElement.prototype.getContext = (() => ctx) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  vi.stubGlobal('requestAnimationFrame', () => 0);
  vi.stubGlobal('cancelAnimationFrame', () => {});
  const s = createScene();
  northwindModel(s);
  settleTweens(s);
  s.userZoomed = true;
  s.cam.x = s.cam.tx = x;
  s.cam.s = s.cam.ts = zoom;
  const r = createRenderer(document.createElement('canvas'), s, hooks());
  calls.clear();
  r.start();
  r.stop();
  return { s, calls };
}

describe('viewport culling', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('keeps a cell whose label can still reach the canvas, and drops one that cannot', () => {
    const { ctx } = countingContext();
    const v = viewOf(ctx, [0, 0, 1000, 1000]);
    const s = createScene();
    s.cam.s = 1;
    const near = addNode(s, { x: 1150, y: 500, label: 'A label of thirty characters..' });
    const far = addNode(s, { x: 1150, y: 500, label: 'A' });
    const below = addNode(s, { x: 500, y: 1100, label: 'A' });
    const above = addNode(s, { x: 500, y: -40, label: 'A' });
    expect(cellInView(s, v, near)).toBe(true);
    expect(cellInView(s, v, far)).toBe(false);
    expect(cellInView(s, v, below)).toBe(false);
    expect(cellInView(s, v, above)).toBe(true);
  });

  it('draws the links that can reach the canvas only', () => {
    const { ctx, calls } = countingContext();
    const v = viewOf(ctx, [0, 0, 1000, 1000]);
    const s = createScene();
    s.cam.s = 1;
    const a = addNode(s, { x: 100, y: 100, alpha: 1 }),
      b = addNode(s, { x: 600, y: 600, alpha: 1 }),
      c = addNode(s, { x: 2000, y: 2000, alpha: 1 }),
      d = addNode(s, { x: 2500, y: 2500, alpha: 1 });
    const seen = addLink(s, a, b, 'rel', 230, 'has'),
      crossing = addLink(s, a, c, 'rel', 230, 'has'),
      away = addLink(s, c, d, 'rel', 230, 'has');
    for (const l of [seen, crossing, away]) l.alpha = 1;
    drawLinks(s, v, 1);
    expect(calls.get('quadraticCurveTo')).toBe(2);
    expect(seen._chip).toBeDefined();
    expect(away._chip).toBeUndefined();
  });

  it('draws no cell and no link when the camera is far from the model', () => {
    // Every cell turns the context once; the regions never do.
    const near = frameAt(0, 0.2);
    expect(near.calls.get('rotate')).toBeGreaterThanOrEqual(near.s.nodes.length);
    expect(near.calls.get('quadraticCurveTo')).toBeGreaterThanOrEqual(near.s.links.length);
    const far = frameAt(1e6, 1);
    expect(far.calls.get('rotate') ?? 0).toBe(0);
    expect(far.calls.get('quadraticCurveTo') ?? 0).toBe(0);
  });
});

describe('cell gradients', () => {
  it('creates one gradient for cells drawn alike', () => {
    const { ctx, calls } = countingContext();
    const v = viewOf(ctx, [0, 0, 1000, 1000]);
    const s = createScene();
    s.cam.s = 1;
    const colour = '#abcdef';
    for (let i = 0; i < 5; i++) drawCell(s, v, addNode(s, { x: 100 + 80 * i, y: 100, color: colour, alpha: 1, label: 'A' }), 1);
    drawCell(s, v, addNode(s, { x: 100, y: 300, color: '#123456', alpha: 1, label: 'B' }), 1);
    expect(calls.get('arc')).toBe(12);
    expect(calls.get('createRadialGradient')).toBeLessThanOrEqual(2);
  });
});
