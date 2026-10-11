/**
 * Canvas theme object, derived from the design tokens of the theme currently applied to the
 * document (ported shape from reference/ontaix-studio-reference.html lines 251-254). `INK`,
 * `INK2` and `CHIP` are rgb triplets used inside `rgba()` strings; the alphas are the renderer's.
 */
import { MIX_BLACK, token } from '../design/tokens';
import { hex, mix } from './colour';

export type ThemeName = 'dark' | 'light';

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

/** Hull and region alphas per theme: the light canvas takes stronger tints to read on warm stone. */
const ALPHAS: Record<ThemeName, Pick<CanvasTheme, 'hullA' | 'domA' | 'domFocusA'>> = {
  dark: { hullA: 0.055, domA: 0.075, domFocusA: 0.12 },
  light: { hullA: 0.05, domA: 0.13, domFocusA: 0.2 },
};

/** `#rrggbb` to the `r,g,b` triplet the renderer puts inside `rgba()`. */
export const triplet = (c: string): string => {
  const n = parseInt(c.slice(1), 16);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
};

/**
 * Builds the theme from the tokens: the page background, text colours for labels, the surface
 * for chips, a label halo in the background colour, a vignette toward black, and the text colour
 * as the company hull. Anything but `light` is dark, as the reference resolved it.
 */
export function themeFor(name: string): CanvasTheme {
  const theme: ThemeName = name === 'light' ? 'light' : 'dark';
  const bg = token('--bg');
  return {
    bg,
    INK: triplet(token('--text')),
    INK2: triplet(token('--text-2')),
    CHIP: triplet(token('--surface')),
    shadow: hex(bg, 0.85),
    vignette: theme === 'light' ? hex(mix(bg, MIX_BLACK, 0.12), 0.5) : hex(mix(bg, MIX_BLACK, 0.35), 0.8),
    hull: token('--text'),
    ...ALPHAS[theme],
  };
}
