/**
 * Constants of the canvas renderer, ported from reference/ontaix-studio-reference.html lines
 * 239-300 and 571. Values are verbatim; a unit test pins them to contracts/design-tokens.json.
 */
import type { DomainKey } from './types';

/** Cell radius. */
export const CELL = 24;

export const C = {
  root: '#d8deee',
  plant: '#8b86cf',
  line: '#3fb8a9',
  product: '#d9a15b',
  material: '#cf7d98',
  supplier: '#7fb6d9',
  customer: '#9fc27a',
  order: '#c9b16b',
  machine: '#5fa3c9',
  conflict: '#d95a68',
} as const;

export const PALETTE = [C.line, C.product, C.plant, C.material, C.supplier, C.customer, C.machine, C.order];

export interface DomainTemplate {
  key: DomainKey;
  name: string;
  owner: string;
  color: string;
}

export const DOMAIN_TEMPLATES: DomainTemplate[] = [
  { key: 'production', name: 'Production', owner: 'Plant operations', color: '#3fb8a9' },
  { key: 'supply', name: 'Supply chain', owner: 'Procurement', color: '#8b86cf' },
  { key: 'sales', name: 'Sales', owner: 'Commercial', color: '#d9a15b' },
  { key: 'logistics', name: 'Logistics', owner: 'Distribution', color: '#d98b6b' },
  { key: 'quality', name: 'Quality', owner: 'Quality assurance', color: '#cf7d98' },
  { key: 'maintenance', name: 'Maintenance', owner: 'Asset management', color: '#7fb6d9' },
  { key: 'finance', name: 'Finance', owner: 'Controlling', color: '#b9b36a' },
  { key: 'people', name: 'People', owner: 'Human resources', color: '#8fbf7a' },
  { key: 'engineering', name: 'Engineering', owner: 'R&D', color: '#c58ad0' },
];

export const DEFAULT_COLORS: Record<string, string> = Object.fromEntries(DOMAIN_TEMPLATES.map((t) => [t.key, t.color]));

/** Radius of the ring the nine domain centres sit on. */
export const DOMAIN_R = Math.max(470, DOMAIN_TEMPLATES.length * 74);

export const GREEN = '#4fc98f';
export const RED = '#d95a68';
export const DEFAULT_BRASS = '#d6bd8a';
export const NEUTRAL = '#a9b3cc';
export const EQUIVALENCE_LINE = '#e6ebf7';

/** Regions render at half resolution on one shared layer. */
export const OFFS = 0.5;

/** Pause between two proposals of a story scene, in milliseconds. */
export const W_ = 880;

export const REDUCED: boolean =
  typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)').matches : false;
export const MOTION = REDUCED ? 0.35 : 1;
