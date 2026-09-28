/**
 * Cell division: a new concept is born by division of an existing cell, then differentiates.
 * Ported from reference/ontaix-studio-reference.html lines 303-309 (`divide`).
 *
 * The three random draws happen in the reference order: birth angle noise, node seed, link
 * seed. A caller that drew them earlier (to send the link seed with the proposal draft) passes
 * them in `o.draws`, and no draw happens here.
 */
import { now, nowDate } from '../runtime/clock';
import { random } from '../runtime/rng';
import { CELL } from './constants';
import { addLink, addNode, domainCentre, domainOf, type SceneState } from './state';
import type { Node } from './types';

/** The random numbers a birth consumes, in draw order. */
export interface BirthDraws {
  /** Angle noise term in [0, 1). */
  noise: number;
  /** Node seed in [0, 100). */
  node: number;
  /** Curve bend of the birth link in [0, 1). */
  link: number;
}

/** Draws the three numbers of a birth from the shared stream, in reference order. */
export const drawBirth = (): BirthDraws => ({ noise: random(), node: random() * 100, link: random() });

export interface DivideOptions {
  /** Domain key of the child; the parent's domain when left out. */
  domain?: string | null;
  angle?: number;
  dist?: number;
  isa?: boolean;
  reverse?: boolean;
  rest?: number;
  label?: string;
  draws?: BirthDraws;
}

export function divide(s: SceneState, parent: Node, label: string, color: string | null, o: DivideOptions = {}): Node {
  const dom = o.domain ? domainOf(s, o.domain, parent.company) : parent.domain;
  const noise = o.draws ? o.draws.noise : random();
  const ang =
    o.angle ??
    (dom ? Math.atan2(domainCentre(dom)[1] - parent.y, domainCentre(dom)[0] - parent.x) + (noise - 0.5) * 1.2 : noise * 6.283);
  const n = addNode(s, {
    label,
    domain: dom,
    company: parent.company,
    color: parent.color,
    cloneColor: parent.color,
    finalColor: color ?? (dom ? dom.color : parent.color),
    labelAlpha: 0,
    x: parent.x,
    y: parent.y,
    seed: o.draws?.node,
    split: {
      from: parent,
      start: now(),
      dur: s.SKIP ? 0.02 : o.dist ? 1.1 : 0.85,
      ang,
      broken: false,
      kicked: false,
      D: Math.max(CELL * 3.1, o.dist || 0),
    },
  });
  const cross = parent.domain !== dom;
  const seed = o.draws?.link;
  n.parent = parent;
  n.birthLink = o.isa
    ? addLink(s, n, parent, 'isa', o.rest ?? (cross ? 300 : 170), 'is a', seed)
    : o.reverse
      ? addLink(s, n, parent, 'rel', o.rest ?? (cross ? 330 : 220), o.label ?? 'relates to', seed)
      : addLink(s, parent, n, 'rel', o.rest ?? (cross ? 330 : 220), o.label ?? 'relates to', seed);
  n.bornAt = nowDate();
  return n;
}
