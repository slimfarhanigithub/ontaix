import { currentSeed, mulberry32, random, seedFromLocation, seedRandom } from './rng';

describe('rng', () => {
  afterEach(() => seedRandom(null));

  it('mulberry32 is deterministic for a seed', () => {
    const a = mulberry32(42),
      b = mulberry32(42);
    const seqA = Array.from({ length: 5 }, () => a());
    const seqB = Array.from({ length: 5 }, () => b());
    expect(seqA).toEqual(seqB);
    for (const x of seqA) expect(x >= 0 && x < 1).toBe(true);
  });

  it('two seeds give two streams', () => {
    expect(mulberry32(1)()).not.toBe(mulberry32(2)());
  });

  it('pins the first draws of seed 42, the harness seed', () => {
    const r = mulberry32(42);
    expect(r()).toBeCloseTo(0.6011037519201636, 12);
    expect(r()).toBeCloseTo(0.44829055899754167, 12);
  });

  it('random() follows the seeded stream in test mode', () => {
    seedRandom(7);
    const expected = mulberry32(7);
    expect(random()).toBe(expected());
    expect(random()).toBe(expected());
    expect(currentSeed()).toBe(7);
  });

  it('reads the seed from the URL before the build-time value', () => {
    expect(seedFromLocation('?seed=12', '3')).toBe(12);
    expect(seedFromLocation('', '3')).toBe(3);
    expect(seedFromLocation('', undefined)).toBeNull();
    expect(seedFromLocation('?seed=abc', undefined)).toBeNull();
  });
});
