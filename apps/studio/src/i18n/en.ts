/**
 * The English dictionary, the source of every Studio label: one file per area, merged here.
 * Values are the exact strings the Studio shows in English; placeholders follow `format.ts`.
 */
import { admin } from './en/admin';
import { auth } from './en/auth';
import { canvas } from './en/canvas';
import { common } from './en/common';
import { demo } from './en/demo';
import { platform } from './en/platform';
import { shell } from './en/shell';
import { teach } from './en/teach';

export const areas = { common, auth, platform, admin, shell, teach, canvas, demo };

export const en = { ...common, ...auth, ...platform, ...admin, ...shell, ...teach, ...canvas, ...demo };
