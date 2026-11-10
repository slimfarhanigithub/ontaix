/**
 * `t(key, params)`: the Studio's label for `key` in the portal language, parameters filled in.
 * Components call `useT()` so they re-render when the language changes; code outside React calls
 * `t` directly and reads the language of the moment. Dates and numbers format through `Intl` in
 * the same language.
 */
import { dictionaries, type MessageKey } from './dictionary';
import { formatMessage, type Params } from './format';
import { languageStore, useLanguage } from './language';

export type { MessageKey } from './dictionary';
export type { Params } from './format';
export { applyLanguage, isLanguage, LANGUAGE_NAMES, LANGUAGES, languageStore, resolveLanguage, useLanguage, type Language } from './language';

export function t(key: MessageKey, params?: Params): string {
  const template = dictionaries[languageStore.language][key] ?? dictionaries.en[key] ?? key;
  return formatMessage(template, params, languageStore.locale);
}

/** `t`, with the calling component re-rendered whenever the portal language changes. */
export function useT(): typeof t {
  useLanguage();
  return t;
}

/** A number with the language's grouping and decimal marks (`1,234.5` in English, `1 234,5` in French). */
export function formatNumber(n: number, options?: Intl.NumberFormatOptions): string {
  return n.toLocaleString(languageStore.locale, options);
}

/** `29 Oct 2026` in English, with the language's month names and order. */
export function formatDate(date: Date | string, options: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' }): string {
  return toDate(date).toLocaleDateString(languageStore.locale, options);
}

/** `14:05:09` in English; the language's time notation. */
export function formatTime(date: Date | string, options?: Intl.DateTimeFormatOptions): string {
  return toDate(date).toLocaleTimeString(languageStore.locale, options);
}

const toDate = (d: Date | string): Date => (d instanceof Date ? d : new Date(d));
