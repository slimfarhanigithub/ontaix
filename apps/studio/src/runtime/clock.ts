/**
 * The single clock of the Studio. The renderer and the store read time only through these
 * functions, so a test harness that fakes `performance` and `Date` controls every frame.
 */

/** Seconds since the time origin, the unit the physics and the animations run in. */
export const now = (): number => performance.now() / 1000;

/** Wall-clock stamp for records such as `bornAt`. */
export const nowDate = (): Date => new Date();
