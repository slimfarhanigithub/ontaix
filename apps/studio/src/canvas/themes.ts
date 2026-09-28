/**
 * Canvas theme object, ported from reference/ontaix-studio-reference.html lines 251-254.
 * `INK`, `INK2` and `CHIP` are rgb triplets used inside `rgba()` strings.
 */

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

export const THEMES: Record<ThemeName, CanvasTheme> = {
  dark: {
    bg: '#070b16',
    INK: '238,242,251',
    INK2: '169,179,204',
    CHIP: '7,11,22',
    shadow: 'rgba(0,0,0,0.7)',
    vignette: 'rgba(3,5,12,0.8)',
    hull: '#dfe6ff',
    hullA: 0.055,
    domA: 0.075,
    domFocusA: 0.12,
  },
  light: {
    bg: '#eef1f7',
    INK: '20,26,46',
    INK2: '74,84,112',
    CHIP: '255,255,255',
    shadow: 'rgba(255,255,255,0.85)',
    vignette: 'rgba(200,206,222,0.55)',
    hull: '#5b6690',
    hullA: 0.05,
    domA: 0.13,
    domFocusA: 0.2,
  },
};

/** Resolves a theme name the way the reference does: anything but `light` is dark. */
export const themeFor = (name: string): CanvasTheme => THEMES[name as ThemeName] || THEMES.dark;
