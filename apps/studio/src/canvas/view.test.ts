import { createView, inView, worldTransform } from './view';

/** A canvas whose context records the transform calls the renderer makes. */
function setup(): { v: ReturnType<typeof createView>; calls: string[] } {
  const calls: string[] = [];
  const ctx = new Proxy({} as CanvasRenderingContext2D, {
    get: (_t, prop) => (prop === 'canvas' ? {} : (...args: unknown[]) => calls.push(`${String(prop)}(${args.join(',')})`)),
    set: () => true,
  });
  HTMLCanvasElement.prototype.getContext = (() => ctx) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  const v = createView(document.createElement('canvas'));
  v.W = 1440;
  v.H = 900;
  v.panelOff = () => false;
  return { v, calls };
}

describe('world transform', () => {
  it('sets the same transform for a camera that moved by less than its step', () => {
    const { v, calls } = setup();
    worldTransform(v, { x: 100.0000003, y: -40.0000002, tx: 0, ty: 0, s: 0.7300000004, ts: 0 });
    const first = calls.splice(0);
    worldTransform(v, { x: 99.9999998, y: -39.9999999, tx: 0, ty: 0, s: 0.7299999997, ts: 0 });
    expect(calls).toEqual(first);
  });

  it('follows a camera that moved by a visible amount', () => {
    const { v, calls } = setup();
    worldTransform(v, { x: 100, y: -40, tx: 0, ty: 0, s: 0.73, ts: 0 });
    const first = calls.splice(0);
    worldTransform(v, { x: 100.01, y: -40, tx: 0, ty: 0, s: 0.731, ts: 0 });
    expect(calls).not.toEqual(first);
  });

  it('records the world rectangle the canvas shows', () => {
    const { v } = setup();
    worldTransform(v, { x: 0, y: 0, tx: 0, ty: 0, s: 1, ts: 0 });
    // The free area is the canvas less the 320 px changes panel, centred at (560, 450).
    expect(v.world).toEqual([-560, -450, 880, 450]);
    expect(inView(v, 900, 0, 950, 10, 0)).toBe(false);
    expect(inView(v, 900, 0, 950, 10, 30)).toBe(true);
  });
});
