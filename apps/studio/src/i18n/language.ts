/**
 * The portal language: which of English, French and German the Studio's own labels, messages,
 * dates and numbers are written in. It belongs to the person (`account.language`), falls back to
 * the browser's language, then to English, and the last language used stays in the browser so
 * the sign-in page opens in it. Ontology content never follows it.
 */
import { useSyncExternalStore } from 'react';

export type Language = 'en' | 'fr' | 'de';

export const LANGUAGES: readonly Language[] = ['en', 'fr', 'de'];

/** Each language named in itself, as the account menu lists them. */
export const LANGUAGE_NAMES: Record<Language, string> = { en: 'English', fr: 'Français', de: 'Deutsch' };

/** The locale `Intl` formats dates and numbers with, per language. */
export const LOCALES: Record<Language, string> = { en: 'en-GB', fr: 'fr-FR', de: 'de-DE' };

/** `localStorage` key of the last language used in this browser. */
export const LANGUAGE_KEY = 'ontaix.language';

export const DEFAULT_LANGUAGE: Language = 'en';

export const isLanguage = (x: unknown): x is Language => x === 'en' || x === 'fr' || x === 'de';

/** The language a browser tag (`fr-CA`, `de`) names, when it is one of the three. */
export function languageOfTag(tag: string | null | undefined): Language | null {
  const primary = (tag || '').toLowerCase().split('-')[0];
  return isLanguage(primary) ? primary : null;
}

/**
 * The account's language when set, else the browser's language when it is one of the three,
 * else English.
 */
export function resolveLanguage(account: Language | null | undefined, browserTag: string | null | undefined = browserLanguage()): Language {
  return account ?? languageOfTag(browserTag) ?? DEFAULT_LANGUAGE;
}

function browserLanguage(): string | null {
  return typeof navigator === 'undefined' ? null : navigator.language;
}

export function readStoredLanguage(): Language | null {
  try {
    const v = localStorage.getItem(LANGUAGE_KEY);
    return isLanguage(v) ? v : null;
  } catch {
    return null;
  }
}

export function writeStoredLanguage(language: Language): void {
  try {
    localStorage.setItem(LANGUAGE_KEY, language);
  } catch {
    // Storage may be unavailable; the language still applies for this page.
  }
}

type Listener = () => void;

class LanguageStore {
  private current: Language = readStoredLanguage() ?? resolveLanguage(null);
  private version = 0;
  private listeners = new Set<Listener>();

  get language(): Language {
    return this.current;
  }

  get locale(): string {
    return LOCALES[this.current];
  }

  subscribe = (fn: Listener): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  getVersion = (): number => this.version;

  /** Makes `language` the portal language: every subscriber re-renders and `<html lang>` follows. */
  set(language: Language): void {
    if (typeof document !== 'undefined') document.documentElement.lang = language;
    if (language === this.current) return;
    this.current = language;
    this.version++;
    for (const fn of this.listeners) fn();
  }
}

export const languageStore = new LanguageStore();

/** At start-up: `<html lang>` takes the language the browser remembers, or the browser's own. */
export function startLanguage(): void {
  languageStore.set(languageStore.language);
}

/** Applies `language` for this page and remembers it for the next sign-in page in this browser. */
export function applyLanguage(language: Language): void {
  languageStore.set(language);
  writeStoredLanguage(language);
}

/** Re-renders the caller when the portal language changes and hands back the language. */
export function useLanguage(): Language {
  useSyncExternalStore(languageStore.subscribe, languageStore.getVersion, languageStore.getVersion);
  return languageStore.language;
}
