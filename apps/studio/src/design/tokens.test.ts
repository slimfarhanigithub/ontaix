/** The code-side tokens mirror tokens.css: the fallback map and the font stacks. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { parseTokens } from './contrast';
import { DEFAULT_ACCENT, FONT_MONO, FONT_SANS, LIGHT_FALLBACK, token } from './tokens';

const tokens = parseTokens(readFileSync(resolve(__dirname, 'tokens.css'), 'utf8'));

describe('tokens.ts mirrors tokens.css', () => {
  it('fallback values', () => {
    for (const [name, value] of Object.entries(LIGHT_FALLBACK)) expect(tokens[name], name).toBe(value);
  });

  it('the default accent is the accent token', () => {
    expect(DEFAULT_ACCENT).toBe(tokens['--accent']);
  });

  it('font stacks start with the families tokens.css names', () => {
    expect(tokens['--font-sans'].startsWith("'Hanken Grotesk Variable'")).toBe(true);
    expect(FONT_SANS.startsWith("'Hanken Grotesk Variable'")).toBe(true);
    expect(tokens['--font-mono'].startsWith("'IBM Plex Mono'")).toBe(true);
    expect(FONT_MONO.startsWith("'IBM Plex Mono'")).toBe(true);
  });

  it('token() falls back to the fallback value when the document defines none', () => {
    expect(token('--accent')).toBe(DEFAULT_ACCENT);
    expect(token('--not-a-token')).toBe('');
  });
});
