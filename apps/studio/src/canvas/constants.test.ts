import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { LIGHT_FALLBACK } from '../design/tokens';
import { C, DEFAULT_BRASS, DOMAIN_TEMPLATES, GREEN, NEUTRAL, PALETTE, RED } from './constants';
import { themeFor, triplet } from './themes';

interface Token {
  $value: unknown;
}
type TokenTree = { [k: string]: TokenTree | Token | string | undefined };

const tokens = JSON.parse(
  readFileSync(resolve(__dirname, '../../../../contracts/design-tokens.json'), 'utf8'),
) as TokenTree;

const value = (path: string): unknown => {
  let cur: unknown = tokens;
  for (const k of path.split('.')) cur = (cur as TokenTree)[k];
  return (cur as Token).$value;
};

describe('canvas constants match contracts/design-tokens.json', () => {
  it('theme alphas, and the light theme derived from the light tokens', () => {
    for (const name of ['dark', 'light'] as const) {
      const th = themeFor(name);
      for (const key of ['hullA', 'domA', 'domFocusA'] as const) expect(th[key], `${name}.${key}`).toEqual(value(`canvas.theme.${name}.${key}`));
    }
    // jsdom has no stylesheet, so themeFor reads the light fallbacks whatever the name.
    const light = themeFor('light');
    expect(light.bg).toBe(LIGHT_FALLBACK['--bg']);
    expect(light.INK).toBe(triplet(LIGHT_FALLBACK['--text']));
    expect(light.INK2).toBe(triplet(LIGHT_FALLBACK['--text-2']));
    expect(light.CHIP).toBe(triplet(LIGHT_FALLBACK['--surface']));
    expect(light.hull).toBe(LIGHT_FALLBACK['--text']);
  });

  it('domain colours follow the categorical order', () => {
    for (const t of DOMAIN_TEMPLATES) expect(t.color, t.key).toBe(value(`domain.${t.key}`));
    expect(PALETTE).toEqual(['accent', 'link', 'good', 'human', 'text-3', 'violet', 'teal', 'orange', 'olive'].map((n) => value(`css.light.${n}`)));
  });

  it('semantic colours', () => {
    expect(GREEN).toBe(value('semantic.green'));
    expect(RED).toBe(value('semantic.red'));
    expect(DEFAULT_BRASS).toBe(value('semantic.brass'));
    expect(NEUTRAL).toBe(value('semantic.neutral-proposal-dot'));
    expect(C.root).toBe(value('semantic.root'));
    expect(C.conflict).toBe(value('semantic.red'));
    for (const k of ['plant', 'line', 'product', 'material', 'supplier', 'customer', 'order', 'machine'] as const)
      expect(C[k], k).toBe(value(`semantic.palette.${k}`));
  });
});
