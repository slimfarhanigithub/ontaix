/** The German dictionary, one file per area, typed against the English source. */
import { admin } from './de/admin';
import { auth } from './de/auth';
import { canvas } from './de/canvas';
import { common } from './de/common';
import { demo } from './de/demo';
import { platform } from './de/platform';
import { shell } from './de/shell';
import { teach } from './de/teach';
import type { Dictionary } from './dictionary';

export const de: Dictionary = { ...common, ...auth, ...platform, ...admin, ...shell, ...teach, ...canvas, ...demo };
