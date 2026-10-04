/** The code-side tokens mirror tokens.css: the light fallback map and the font stacks. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { parseTokens } from './contrast';
import { DEFAULT_ACCENT, FONT_MONO, FONT_SANS, LIGHT_FALLBACK, token } from './tokens';

const themes = parseTokens(readFileSync(resolve(__dirname, 'tokens.css'), 'utf8'));

describe('tokens.ts mirrors tokens.css', () => {
  it('light fallback values', () => {
    for (const [name, value] of Object.entries(LIGHT_FALLBACK)) expect(themes.light[name], name).toBe(value);
  });

  it('the default accent is the light accent', () => {
    expect(DEFAULT_ACCENT).toBe(themes.light['--accent']);
  });

  it('font stacks start with the families tokens.css names', () => {
    expect(themes.light['--font-sans'].startsWith("'Hanken Grotesk Variable'")).toBe(true);
    expect(FONT_SANS.startsWith("'Hanken Grotesk Variable'")).toBe(true);
    expect(themes.light['--font-mono'].startsWith("'IBM Plex Mono'")).toBe(true);
    expect(FONT_MONO.startsWith("'IBM Plex Mono'")).toBe(true);
  });

  it('token() falls back to the light value when the document defines none', () => {
    expect(token('--accent')).toBe(DEFAULT_ACCENT);
    expect(token('--not-a-token')).toBe('');
  });
});
