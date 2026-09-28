import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { C, DEFAULT_BRASS, DOMAIN_TEMPLATES, GREEN, RED } from './constants';
import { THEMES } from './themes';

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
  it('theme objects', () => {
    for (const name of ['dark', 'light'] as const) {
      for (const key of Object.keys(THEMES[name]) as (keyof typeof THEMES.dark)[]) {
        expect(THEMES[name][key], `${name}.${key}`).toEqual(value(`canvas.theme.${name}.${key}`));
      }
    }
  });

  it('domain colours', () => {
    for (const t of DOMAIN_TEMPLATES) expect(t.color, t.key).toBe(value(`domain.${t.key}`));
  });

  it('semantic colours', () => {
    expect(GREEN).toBe(value('semantic.green'));
    expect(RED).toBe(value('semantic.red'));
    expect(DEFAULT_BRASS).toBe(value('semantic.brass'));
    expect(C.root).toBe(value('semantic.root'));
    expect(C.conflict).toBe(value('semantic.red'));
    for (const k of ['plant', 'line', 'product', 'material', 'supplier', 'customer', 'order', 'machine'] as const)
      expect(C[k], k).toBe(value(`semantic.palette.${k}`));
  });
});
