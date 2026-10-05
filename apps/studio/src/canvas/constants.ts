/**
 * Constants of the canvas renderer: geometry and motion ported from
 * reference/ontaix-studio-reference.html lines 239-300 and 571, colours from the design tokens
 * (their light values; the renderer draws each through `themedColour`). A unit test pins the
 * colours to contracts/design-tokens.json.
 */
import { CATEGORICAL_LIGHT, LIGHT_FALLBACK } from '../design/tokens';
import type { TemplateKey } from './types';

/** Cell radius. */
export const CELL = 24;

/** The named colours of the model: the root cell, the conflict red, and the first eight categorical colours after the accent. */
export const C = {
  root: LIGHT_FALLBACK['--text-4'],
  line: CATEGORICAL_LIGHT[0],
  plant: CATEGORICAL_LIGHT[1],
  product: CATEGORICAL_LIGHT[2],
  material: CATEGORICAL_LIGHT[3],
  supplier: CATEGORICAL_LIGHT[4],
  customer: CATEGORICAL_LIGHT[5],
  machine: CATEGORICAL_LIGHT[6],
  order: CATEGORICAL_LIGHT[7],
  conflict: LIGHT_FALLBACK['--danger'],
} as const;

/** Colours a new custom domain takes, in the categorical order. */
export const PALETTE = [...CATEGORICAL_LIGHT];

export interface DomainTemplate {
  key: TemplateKey;
  name: string;
  owner: string;
  color: string;
}

export const DOMAIN_TEMPLATES: DomainTemplate[] = [
  { key: 'production', name: 'Production', owner: 'Plant operations', color: CATEGORICAL_LIGHT[0] },
  { key: 'supply', name: 'Supply chain', owner: 'Procurement', color: CATEGORICAL_LIGHT[1] },
  { key: 'sales', name: 'Sales', owner: 'Commercial', color: CATEGORICAL_LIGHT[2] },
  { key: 'logistics', name: 'Logistics', owner: 'Distribution', color: CATEGORICAL_LIGHT[3] },
  { key: 'quality', name: 'Quality', owner: 'Quality assurance', color: CATEGORICAL_LIGHT[4] },
  { key: 'maintenance', name: 'Maintenance', owner: 'Asset management', color: CATEGORICAL_LIGHT[5] },
  { key: 'finance', name: 'Finance', owner: 'Controlling', color: CATEGORICAL_LIGHT[6] },
  { key: 'people', name: 'People', owner: 'Human resources', color: CATEGORICAL_LIGHT[7] },
  { key: 'engineering', name: 'Engineering', owner: 'R&D', color: CATEGORICAL_LIGHT[8] },
];

export const DEFAULT_COLORS: Record<string, string> = Object.fromEntries(DOMAIN_TEMPLATES.map((t) => [t.key, t.color]));

/** Radius of the ring the nine domain centres sit on. */
export const DOMAIN_R = Math.max(470, DOMAIN_TEMPLATES.length * 74);

/** Ring positions 0 to TEMPLATE_COUNT - 1 belong to the templates; custom domains take 9 to 63. */
export const TEMPLATE_COUNT = DOMAIN_TEMPLATES.length;
/** Most domains a tenant may hold, the templates included. */
export const MAX_DOMAINS = 64;
/** Custom domains sit between the templates on the same ring, then on outer rings this far apart. */
export const CUSTOM_RING_STEP = 300;

/** The approval rim and the rejection fade, stored as light values and drawn through `themedColour`. */
export const GREEN = LIGHT_FALLBACK['--good'];
export const RED = LIGHT_FALLBACK['--danger'];
/** The data-source colour a tenant starts with. */
export const DEFAULT_BRASS = LIGHT_FALLBACK['--source'];
/** The proposal dot and drawer fallback colour. */
export const NEUTRAL = LIGHT_FALLBACK['--text-3'];

/** Regions render at half resolution on one shared layer. */
export const OFFS = 0.5;

export const REDUCED: boolean =
  typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)').matches : false;
export const MOTION = REDUCED ? 0.35 : 1;
