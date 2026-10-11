/**
 * The accessibility contract of the tokens: text on every neutral surface, each status text on
 * its own tint, the gold primary pair and the focus ring. A pair below its threshold fails the
 * build unless the KNOWN_BELOW_AA ledger lists it; a listed pair that starts passing fails the
 * build too, until its row is removed.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { contrast, parseTokens } from './contrast';

const tokens = parseTokens(readFileSync(resolve(__dirname, 'tokens.css'), 'utf8'));

const NEUTRALS = ['--bg', '--surface', '--surface-2', '--hover', '--rowhover', '--chip', '--subtle'];
const SOFT_TINTS = ['--accent-soft', '--human-soft', '--good-soft', '--danger-soft', '--info-bg'];
const AA = 4.5;
const AA_LARGE = 3;

interface Pair {
  fg: string;
  bg: string;
  min: number;
}

/** Every pair the design system promises, with its threshold. */
const CHECKED: Pair[] = [];
for (const fg of ['--text', '--text-2', '--text-3', '--text-4', '--good', '--human', '--accent', '--danger'])
  for (const bg of NEUTRALS) CHECKED.push({ fg, bg, min: AA });
for (const bg of SOFT_TINTS) CHECKED.push({ fg: '--text-3', bg, min: AA });
CHECKED.push({ fg: '--good', bg: '--good-soft', min: AA });
CHECKED.push({ fg: '--human-text', bg: '--human-soft', min: AA });
CHECKED.push({ fg: '--accent-text', bg: '--accent-soft', min: AA });
CHECKED.push({ fg: '--danger', bg: '--danger-soft', min: AA });
CHECKED.push({ fg: '--info-text', bg: '--info-bg', min: AA });
CHECKED.push({ fg: '--bg', bg: '--human-text', min: AA });
CHECKED.push({ fg: '--bg', bg: '--human', min: AA });
CHECKED.push({ fg: '--bg', bg: '--accent', min: AA });
for (const bg of NEUTRALS) CHECKED.push({ fg: '--link', bg, min: AA_LARGE });

/**
 * Pairs below their threshold on purpose, each with the rule that keeps them harmless. The id
 * names the row in docs/design-system.md.
 */
const KNOWN_BELOW_AA: { id: string; fg: string; bg: string[]; guidance: string }[] = [
  { id: 'A11Y-C1', fg: '--text-4', bg: NEUTRALS, guidance: 'Decorative or disabled text only' },
  { id: 'A11Y-C2', fg: '--good', bg: NEUTRALS, guidance: 'Icons, dots and badges, or paired with a --text label' },
  { id: 'A11Y-C3', fg: '--human', bg: NEUTRALS, guidance: 'Gold text uses --human-text' },
  { id: 'A11Y-C5', fg: '--text-3', bg: ['--accent-soft', '--human-soft'], guidance: 'Text on a tint uses the tint’s own -text token' },
  { id: 'A11Y-C6', fg: '--bg', bg: ['--human'], guidance: 'A gold fill under light text uses --human-text, never --human' },
  { id: 'A11Y-C7', fg: '--good', bg: ['--good-soft'], guidance: 'A success badge shows a dot or icon in --good with its label in --text' },
];

function ledgered(p: Pair): boolean {
  return KNOWN_BELOW_AA.some((k) => k.fg === p.fg && k.bg.includes(p.bg));
}

const ratio = (p: Pair): number => contrast(tokens[p.fg], tokens[p.bg]);
const describePair = (p: Pair): string => `${p.fg} on ${p.bg}`;

describe('tokens.css contrast', () => {
  it('parses the raw block and the aliases', () => {
    expect(tokens['--bg']).toBe('#f5f5f5');
    expect(tokens['--ink']).toBe(tokens['--text']);
    expect(tokens['--line']).toBe(tokens['--border']);
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
      const hit = CHECKED.some((p) => ledgered(p) && p.fg === k.fg);
      expect(hit, `${k.id} ${k.fg} on ${k.bg} matches no checked pair`).toBe(true);
    }
  });
});
