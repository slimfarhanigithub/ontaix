/** The three dictionaries by language and the key type every `t` call is checked against. */
import { de } from './de';
import { en } from './en';
import { fr } from './fr';
import type { Language } from './language';
import type { Translation } from './translation';

export type Dictionary = Translation<typeof en>;

export type MessageKey = keyof Dictionary;

export const dictionaries: Record<Language, Dictionary> = { en, fr, de };
