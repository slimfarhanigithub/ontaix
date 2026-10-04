/**
 * The design tokens as code: the font stacks the canvas draws with, the default accent, and a
 * runtime reader for anything that cannot use `var()` (canvas fills, SVG attributes). The values
 * mirror tokens.css, which stays the source of truth; tokens.test.ts pins them to it.
 */

/** The UI typeface, as a CSS font-family list the canvas `ctx.font` shorthand accepts. */
export const FONT_SANS = "'Hanken Grotesk Variable', ui-sans-serif, system-ui, sans-serif";
/** The monospace typeface for ids, hashes, column paths and timestamps. */
export const FONT_MONO = "'IBM Plex Mono', ui-monospace, Menlo, Consolas, monospace";

/** The brand accent a tenant starts with (light theme); crimson, chrome only. */
export const DEFAULT_ACCENT = '#d30c55';

/** Light-theme values of the tokens read at runtime, so a reader never gets an empty string. */
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
};

/**
 * Reads a token from the document's computed style, in the theme currently applied, falling back
 * to its light value when the document has none (tests, a detached canvas).
 */
export function token(name: keyof typeof LIGHT_FALLBACK | string): string {
  if (typeof document !== 'undefined') {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    if (v) return v;
  }
  return LIGHT_FALLBACK[name] ?? '';
}
