import { describe, expect, it } from 'vitest';
import { sentencesOf, skippedOf } from './extract';

const nonblank = (pieces: string[]) => pieces.join('').replace(/\s/g, '');

describe('mock document sentences', () => {
  it('cuts a long sentence after a clause boundary and keeps every piece', () => {
    const clause = 'Insight delivers managed data platforms for energy clients across the region, and each team owns reporting';
    const long = Array(6).fill(clause).join('; ') + '.';

    const pieces = sentencesOf(long);

    expect(pieces.join(' ')).toBe(long);
    expect(pieces.length).toBeGreaterThan(1);
    expect(pieces.every((p) => p.length >= 13 && p.length <= 399)).toBe(true);
    expect(pieces.slice(0, -1).every((p) => p.endsWith(';'))).toBe(true);
    expect(skippedOf(long)).toBe(0);
  });

  it('never leaves a tail too short to keep', () => {
    for (let tail = 1; tail < 40; tail++)
      for (const sentence of ['a'.repeat(396) + '; ' + 'b'.repeat(tail), 'a'.repeat(396) + ' ' + 'b'.repeat(tail)]) {
        expect(nonblank(sentencesOf(sentence))).toBe(nonblank([sentence]));
        expect(skippedOf(sentence)).toBe(0);
      }
  });

  it('counts only the short pieces as skipped', () => {
    expect(skippedOf('Short one. ' + 'x'.repeat(900) + '.')).toBe(1);
    expect(sentencesOf('x'.repeat(900)).join('')).toBe('x'.repeat(900));
  });
});
