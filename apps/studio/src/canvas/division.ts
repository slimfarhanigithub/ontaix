/**
 * Cell division: a new concept is born by division of an existing cell, then differentiates.
 * Ported from reference/ontaix-studio-reference.html lines 303-309 (`divide`).
 *
 * The three random draws happen in the reference order: birth angle, node seed, link seed.
 */
import { now, nowDate } from '../runtime/clock';
import { random } from '../runtime/rng';
import { CELL } from './constants';
import { addLink, addNode, domainCentre, domainOf, type SceneState } from './state';
import type { Node } from './types';

export interface DivideOptions {
  /** Domain key of the child; the parent's domain when left out. */
  domain?: string | null;
  angle?: number;
  dist?: number;
  isa?: boolean;
  reverse?: boolean;
  rest?: number;
  label?: string;
}

export function divide(s: SceneState, parent: Node, label: string, color: string | null, o: DivideOptions = {}): Node {
  const dom = o.domain ? domainOf(s, o.domain, parent.company) : parent.domain;
  const ang =
    o.angle ??
    (dom
      ? Math.atan2(domainCentre(dom)[1] - parent.y, domainCentre(dom)[0] - parent.x) + (random() - 0.5) * 1.2
      : random() * 6.283);
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
  n.parent = parent;
  n.birthLink = o.isa
    ? addLink(s, n, parent, 'isa', o.rest ?? (cross ? 300 : 170), 'is a')
    : o.reverse
      ? addLink(s, n, parent, 'rel', o.rest ?? (cross ? 330 : 220), o.label ?? 'relates to')
      : addLink(s, parent, n, 'rel', o.rest ?? (cross ? 330 : 220), o.label ?? 'relates to');
  n.bornAt = nowDate();
  return n;
}
