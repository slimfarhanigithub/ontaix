/**
 * The accessibility contract of the tokens: text on every neutral surface, each status text on
 * its own tint, the gold primary pair and the focus ring, in both themes. A pair below its
 * threshold fails the build unless the KNOWN_BELOW_AA ledger lists it; a listed pair that
 * starts passing fails the build too, until its row is removed.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { contrast, parseTokens, type ThemeName } from './contrast';

const themes = parseTokens(readFileSync(resolve(__dirname, 'tokens.css'), 'utf8'));

const NEUTRALS = ['--bg', '--surface', '--surface-2', '--hover', '--rowhover', '--chip', '--subtle'];
const SOFT_TINTS = ['--accent-soft', '--human-soft', '--good-soft', '--danger-soft', '--info-bg'];
const AA = 4.5;
const AA_LARGE = 3;

interface Pair {
  theme: ThemeName;
  fg: string;
  bg: string;
  min: number;
}

/** Every pair the design system promises, with its threshold. */
const CHECKED: Pair[] = [];
for (const theme of ['light', 'dark'] as const) {
  for (const fg of ['--text', '--text-2', '--text-3', '--text-4', '--good', '--human', '--accent', '--danger'])
    for (const bg of NEUTRALS) CHECKED.push({ theme, fg, bg, min: AA });
  for (const bg of SOFT_TINTS) CHECKED.push({ theme, fg: '--text-3', bg, min: AA });
  CHECKED.push({ theme, fg: '--good', bg: '--good-soft', min: AA });
  CHECKED.push({ theme, fg: '--human-text', bg: '--human-soft', min: AA });
  CHECKED.push({ theme, fg: '--accent-text', bg: '--accent-soft', min: AA });
  CHECKED.push({ theme, fg: '--danger', bg: '--danger-soft', min: AA });
  CHECKED.push({ theme, fg: '--info-text', bg: '--info-bg', min: AA });
  CHECKED.push({ theme, fg: '--bg', bg: '--human-text', min: AA });
  CHECKED.push({ theme, fg: '--bg', bg: '--human', min: AA });
  CHECKED.push({ theme, fg: '--bg', bg: '--accent', min: AA });
  for (const bg of NEUTRALS) CHECKED.push({ theme, fg: '--link', bg, min: AA_LARGE });
}

/**
 * Pairs below their threshold on purpose, each with the rule that keeps them harmless. The id
 * names the row in docs/design-system.md.
 */
const KNOWN_BELOW_AA: { id: string; theme: ThemeName | 'both'; fg: string; bg: string[]; guidance: string }[] = [
  { id: 'A11Y-C1', theme: 'both', fg: '--text-4', bg: NEUTRALS, guidance: 'Decorative or disabled text only' },
  { id: 'A11Y-C2', theme: 'light', fg: '--good', bg: NEUTRALS, guidance: 'Icons, dots and badges, or paired with a --text label' },
  { id: 'A11Y-C3', theme: 'light', fg: '--human', bg: NEUTRALS, guidance: 'Gold text uses --human-text' },
  { id: 'A11Y-C4', theme: 'dark', fg: '--accent', bg: ['--surface-2', '--hover', '--chip'], guidance: 'On the recessed dark neutrals, accent text uses --accent-text; fills stay' },
  { id: 'A11Y-C4', theme: 'dark', fg: '--danger', bg: ['--surface-2', '--hover', '--chip'], guidance: 'On the recessed dark neutrals, red text pairs with an icon or a --text label' },
  { id: 'A11Y-C5', theme: 'light', fg: '--text-3', bg: ['--accent-soft', '--human-soft'], guidance: 'Text on a tint uses the tint’s own -text token' },
  { id: 'A11Y-C6', theme: 'light', fg: '--bg', bg: ['--human'], guidance: 'A gold fill under light text uses --human-text, never --human' },
  { id: 'A11Y-C7', theme: 'light', fg: '--good', bg: ['--good-soft'], guidance: 'A success badge shows a dot or icon in --good with its label in --text' },
];

function ledgered(p: Pair): boolean {
  return KNOWN_BELOW_AA.some((k) => (k.theme === 'both' || k.theme === p.theme) && k.fg === p.fg && k.bg.includes(p.bg));
}

const ratio = (p: Pair): number => contrast(themes[p.theme][p.fg], themes[p.theme][p.bg]);
const describePair = (p: Pair): string => `${p.theme} ${p.fg} on ${p.bg}`;

describe('tokens.css contrast', () => {
  it('parses both themes with the same token names', () => {
    expect(Object.keys(themes.dark).sort()).toEqual(Object.keys(themes.light).sort());
    expect(themes.light['--bg']).toBe('#f5f5f5');
    expect(themes.dark['--bg']).toBe('#1b1f2a');
    expect(themes.light['--ink']).toBe(themes.light['--text']);
    expect(themes.dark['--line']).toBe(themes.dark['--border']);
  });

  it.each(CHECKED.filter((p) => !ledgered(p)).map((p) => [describePair(p), p] as const))('%s meets its threshold', (_, p) => {
    expect(ratio(p), describePair(p)).toBeGreaterThanOrEqual(p.min);
  });

  it('every ledger row still describes a pair below AA', () => {
    const passing = CHECKED.filter((p) => ledgered(p) && ratio(p) >= p.min).map((p) => `${describePair(p)} = ${ratio(p).toFixed(2)}`);
    expect(passing, 'remove these rows from KNOWN_BELOW_AA and docs/design-system.md').toEqual([]);
  });

  it('every ledger row matches at least one checked pair', () => {
    for (const k of KNOWN_BELOW_AA) {
      const hit = CHECKED.some((p) => ledgered(p) && p.fg === k.fg && (k.theme === 'both' || p.theme === k.theme));
      expect(hit, `${k.id} ${k.theme} ${k.fg} on ${k.bg} matches no checked pair`).toBe(true);
    }
  });
});
