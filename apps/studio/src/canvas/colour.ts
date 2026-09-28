/**
 * Colour and easing helpers, ported from reference/ontaix-studio-reference.html lines 245-247.
 */

/** `#rrggbb` to `rgba(r,g,b,a)`. */
export const hex = (c: string, a: number): string => {
  const n = parseInt(c.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

/** Linear mix of two `#rrggbb` colours, `t` toward `b`. */
export const mix = (a: string, b: string, t: number): string => {
  const A = parseInt(a.slice(1), 16),
    B = parseInt(b.slice(1), 16);
  const ch = (s: number) => Math.round(((A >> s) & 255) * (1 - t) + ((B >> s) & 255) * t);
  return `#${((ch(16) << 16) | (ch(8) << 8) | ch(0)).toString(16).padStart(6, '0')}`;
};

/** Cubic in-out easing. */
export const ease = (t: number): number => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export const clamp = (v: number, a: number, b: number): number => Math.max(a, Math.min(b, v));
