/** The French dictionary, one file per area, typed against the English source. */
import type { Dictionary } from './dictionary';
import { admin } from './fr/admin';
import { auth } from './fr/auth';
import { canvas } from './fr/canvas';
import { common } from './fr/common';
import { demo } from './fr/demo';
import { platform } from './fr/platform';
import { shell } from './fr/shell';
import { teach } from './fr/teach';

export const fr: Dictionary = { ...common, ...auth, ...platform, ...admin, ...shell, ...teach, ...canvas, ...demo };
