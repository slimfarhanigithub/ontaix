/**
 * The design tokens as code: the font stacks the canvas draws with, the default accent, the
 * categorical order, and a runtime reader for anything that cannot use `var()` (canvas fills,
 * SVG attributes, inline styles). The values mirror tokens.css, which stays the source of truth;
 * tokens.test.ts pins them to it.
 */

/** The UI typeface, as a CSS font-family list the canvas `ctx.font` shorthand accepts. */
export const FONT_SANS = "'Hanken Grotesk Variable', ui-sans-serif, system-ui, sans-serif";
/** The monospace typeface for ids, hashes, column paths and timestamps. */
export const FONT_MONO = "'IBM Plex Mono', ui-monospace, Menlo, Consolas, monospace";

/** The brand accent a tenant starts with; crimson, chrome only. */
export const DEFAULT_ACCENT = '#d30c55';

/** The ends of the mixes the canvas shades with: highlights toward white, rims toward black. */
export const MIX_WHITE = '#ffffff';
export const MIX_BLACK = '#000000';

/** The values of the tokens read at runtime, so a reader never gets an empty string. */
export const LIGHT_FALLBACK: Record<string, string> = {
  '--bg': '#f5f5f5',
  '--surface': '#ffffff',
  '--surface-2': '#f3f1ef',
  '--chip': '#f3f1ef',
  '--border': '#edeae7',
  '--border-strong': '#e5e1dd',
  '--text': '#2b2724',
  '--text-2': '#57534e',
  '--text-3': '#6f6a64',
  '--text-4': '#a8a29c',
  '--accent': '#d30c55',
  '--accent-soft': '#fce1eb',
  '--accent-text': '#a80a44',
  '--human': '#a07621',
  '--human-soft': '#f1e4c3',
  '--human-text': '#7a5a19',
  '--link': '#2563eb',
  '--good': '#0e8a6a',
  '--good-soft': '#dcf0e9',
  '--danger': '#c0181d',
  '--danger-soft': '#fbe9e9',
  '--violet': '#7c3aed',
  '--teal': '#0e7490',
  '--orange': '#c2410c',
  '--olive': '#4d7c0f',
  '--source': '#d6bd8a',
};

/** The categorical order: domain products and series take these tokens in turn. */
export const CATEGORICAL = ['--accent', '--link', '--good', '--human', '--text-3', '--violet', '--teal', '--orange', '--olive'] as const;

/** Values of the categorical tokens, in order; the stored default colour of each template. */
export const CATEGORICAL_LIGHT: string[] = CATEGORICAL.map((name) => LIGHT_FALLBACK[name]);

const cache = new Map<string, string>();

/**
 * Reads a token from the document's computed style, falling back to its value in LIGHT_FALLBACK
 * when the document has none (tests, a detached canvas). Values are cached, so a renderer may call
 * this every frame.
 */
export function token(name: keyof typeof LIGHT_FALLBACK | string): string {
  if (typeof document === 'undefined') return LIGHT_FALLBACK[name] ?? '';
  const hit = cache.get(name);
  if (hit !== undefined) return hit;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || LIGHT_FALLBACK[name] || '';
  cache.set(name, v);
  return v;
}

const tokenOfLight = new Map<string, string>(Object.entries(LIGHT_FALLBACK).map(([name, value]) => [value, name]));

/**
 * The colour to draw a stored colour with: a stored default (one of the token values) follows its
 * token, so a rebrand of the tokens reaches it; a tenant's own colour is drawn as it is.
 */
export function themedColour(stored: string): string {
  const name = tokenOfLight.get(stored.toLowerCase());
  return name ? token(name) : stored;
}
