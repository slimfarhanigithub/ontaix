/**
 * Reads tokens.css from disk, resolves each theme's custom properties through their `var()`
 * chains, and measures WCAG contrast between them. Used by the tests only; the browser reads the
 * same file through the stylesheet.
 */

export type ThemeName = 'light' | 'dark';

/** Every custom property of one theme, resolved to its literal value. */
export type Tokens = Record<string, string>;

const LIGHT_SELECTOR = ':root';
const DARK_SELECTOR = ":root[data-theme='dark']";

/** Parses the stylesheet: the raw blocks of each theme, then the alias blocks, in file order. */
export function parseTokens(css: string): Record<ThemeName, Tokens> {
  const blocks = [...css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selectors: m[1].split(',').map((s) => s.trim()),
    declarations: [...m[2].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(([, name, value]) => [name, value.trim()] as const),
  }));
  const raw: Record<ThemeName, Tokens> = { light: {}, dark: {} };
  for (const block of blocks) {
    const forLight = block.selectors.includes(LIGHT_SELECTOR);
    const forDark = block.selectors.includes(DARK_SELECTOR);
    for (const [name, value] of block.declarations) {
      if (forLight) raw.light[name] = value;
      if (forDark) raw.dark[name] = value;
    }
  }
  // Dark inherits every light declaration it does not override, as the cascade does.
  raw.dark = { ...raw.light, ...raw.dark };
  return { light: resolveAll(raw.light), dark: resolveAll(raw.dark) };
}

function resolveAll(tokens: Tokens): Tokens {
  const out: Tokens = {};
  for (const name of Object.keys(tokens)) out[name] = resolve(tokens, name, 0);
  return out;
}

function resolve(tokens: Tokens, name: string, depth: number): string {
  if (depth > 20) throw new Error(`var() chain too deep at ${name}`);
  const value = tokens[name];
  if (value === undefined) throw new Error(`unknown token ${name}`);
  return value.replace(/var\((--[\w-]+)\)/g, (_, ref: string) => resolve(tokens, ref, depth + 1));
}

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

/** `#rgb`, `#rrggbb`, `rgb()` and `rgba()` (the alpha ignored) to channels 0 to 255. */
export function toRgb(value: string): Rgb {
  const v = value.trim();
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(v);
  if (hex) {
    const h = hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join('') : hex[1];
    const n = parseInt(h, 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }
  const fn = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i.exec(v);
  if (fn) return { r: Number(fn[1]), g: Number(fn[2]), b: Number(fn[3]) };
  throw new Error(`not an opaque colour: ${value}`);
}

/** WCAG relative luminance. */
export function luminance({ r, g, b }: Rgb): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** WCAG contrast ratio between two opaque colours, 1 to 21. */
export function contrast(a: string, b: string): number {
  const la = luminance(toRgb(a));
  const lb = luminance(toRgb(b));
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}
