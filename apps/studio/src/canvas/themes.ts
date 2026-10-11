/**
 * Canvas theme object, derived from the design tokens (ported shape from
 * reference/ontaix-studio-reference.html lines 251-254). `INK`, `INK2` and `CHIP` are rgb
 * triplets used inside `rgba()` strings; the alphas are the renderer's.
 */
import { MIX_BLACK, token } from '../design/tokens';
import { hex, mix } from './colour';

export interface CanvasTheme {
  bg: string;
  INK: string;
  INK2: string;
  CHIP: string;
  shadow: string;
  vignette: string;
  hull: string;
  hullA: number;
  domA: number;
  domFocusA: number;
}

/** Hull and region alphas: tints strong enough to read on warm stone. */
const ALPHAS: Pick<CanvasTheme, 'hullA' | 'domA' | 'domFocusA'> = { hullA: 0.05, domA: 0.13, domFocusA: 0.2 };

/** `#rrggbb` to the `r,g,b` triplet the renderer puts inside `rgba()`. */
export const triplet = (c: string): string => {
  const n = parseInt(c.slice(1), 16);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
};

/**
 * Builds the theme from the tokens: the page background, text colours for labels, the surface
 * for chips, a label halo in the background colour, a vignette toward black, and the text colour
 * as the company hull.
 */
export function canvasTheme(): CanvasTheme {
  const bg = token('--bg');
  return {
    bg,
    INK: triplet(token('--text')),
    INK2: triplet(token('--text-2')),
    CHIP: triplet(token('--surface')),
    shadow: hex(bg, 0.85),
    vignette: hex(mix(bg, MIX_BLACK, 0.12), 0.5),
    hull: token('--text'),
    ...ALPHAS,
  };
}
