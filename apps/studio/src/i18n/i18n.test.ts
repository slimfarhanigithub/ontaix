import { act, renderHook } from '@testing-library/react';

import { dictionaries } from './dictionary';
import { areas, en } from './en';
import { formatMessage, paramNames } from './format';
import { formatDate, formatNumber, t, useT } from './i18n';
import { applyLanguage, LANGUAGE_KEY, languageStore, readStoredLanguage, resolveLanguage, startLanguage, writeStoredLanguage } from './language';

afterEach(() => {
  act(() => applyLanguage('en'));
  localStorage.clear();
});

describe('formatMessage', () => {
  it('fills parameters and leaves a missing one visible', () => {
    expect(formatMessage('Teach {name}…', { name: 'Northwind' }, 'en-GB')).toBe('Teach Northwind…');
    expect(formatMessage('Teach {name}…', {}, 'en-GB')).toBe('Teach {name}…');
    expect(formatMessage('No braces', undefined, 'en-GB')).toBe('No braces');
  });

  it('picks the plural branch of the locale, an exact branch first', () => {
    const en = 'Reject {n} {n, plural, one {proposal} other {proposals}}?';
    expect(formatMessage(en, { n: 1 }, 'en-GB')).toBe('Reject 1 proposal?');
    expect(formatMessage(en, { n: 3 }, 'en-GB')).toBe('Reject 3 proposals?');
    expect(formatMessage(en, { n: 0 }, 'en-GB')).toBe('Reject 0 proposals?');
    const fr = '{n, plural, one {# proposition} other {# propositions}}';
    expect(formatMessage(fr, { n: 0 }, 'fr-FR')).toBe('0 proposition');
    expect(formatMessage(fr, { n: 2 }, 'fr-FR')).toBe('2 propositions');
    expect(formatMessage('{n, plural, =0 {none} one {# item} other {# items}}', { n: 0 }, 'en-GB')).toBe('none');
    expect(formatMessage('{n, plural, one {{name} once} other {{name} # times}}', { n: 2, name: 'Ana' }, 'en-GB')).toBe('Ana 2 times');
  });

  it('lists the parameters a template uses', () => {
    expect(paramNames('Hello {name}, {n, plural, one {# {thing}} other {# things}}')).toEqual(['n', 'name', 'thing']);
    expect(paramNames('plain')).toEqual([]);
  });
});

describe('dictionaries', () => {
  const keys = Object.keys(en) as (keyof typeof en)[];

  it('hold strings for every English key, in every language', () => {
    expect(keys.length).toBeGreaterThan(0);
    for (const language of ['fr', 'de'] as const) {
      const dict = dictionaries[language] as Record<string, string>;
      const missing = keys.filter((k) => typeof dict[k] !== 'string' || dict[k].trim() === '');
      expect(missing, `${language} lacks`).toEqual([]);
      const extra = Object.keys(dict).filter((k) => !(k in en));
      expect(extra, `${language} adds`).toEqual([]);
    }
  });

  it('keep the parameters of the English text', () => {
    for (const language of ['fr', 'de'] as const) {
      const dict = dictionaries[language] as Record<string, string>;
      const wrong = keys.filter((k) => paramNames(dict[k]).join() !== paramNames(en[k]).join());
      expect(wrong, `${language} parameters`).toEqual([]);
    }
  });

  it('have no empty English value and no key shared by two areas', () => {
    expect(keys.filter((k) => en[k].trim() === '')).toEqual([]);
    const counted = Object.values(areas as Record<string, object>).reduce((n, area) => n + Object.keys(area).length, 0);
    expect(counted).toBe(keys.length);
  });

  it('use the section sign nowhere', () => {
    for (const dict of Object.values(dictionaries)) for (const v of Object.values(dict)) expect(v).not.toContain('§');
  });
});

describe('language resolution', () => {
  it('takes the account, then the browser, then English', () => {
    expect(resolveLanguage('de', 'fr-FR')).toBe('de');
    expect(resolveLanguage(null, 'fr-CA')).toBe('fr');
    expect(resolveLanguage(undefined, 'de')).toBe('de');
    expect(resolveLanguage(null, 'es-ES')).toBe('en');
    expect(resolveLanguage(null, null)).toBe('en');
  });

  it('remembers the last language in localStorage and survives a failing storage', () => {
    expect(readStoredLanguage()).toBeNull();
    writeStoredLanguage('fr');
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe('fr');
    expect(readStoredLanguage()).toBe('fr');
    localStorage.setItem(LANGUAGE_KEY, 'xx');
    expect(readStoredLanguage()).toBeNull();
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => applyLanguage('de')).not.toThrow();
    expect(languageStore.language).toBe('de');
    spy.mockRestore();
  });

  it('sets html lang at start and on every change', () => {
    startLanguage();
    expect(document.documentElement.lang).toBe('en');
    applyLanguage('fr');
    expect(document.documentElement.lang).toBe('fr');
  });
});

describe('t', () => {
  it('translates with the language of the moment and re-renders hooks', () => {
    expect(t('common.cancel')).toBe('Cancel');
    const { result } = renderHook(() => useT()('common.cancel'));
    expect(result.current).toBe('Cancel');
    act(() => applyLanguage('de'));
    expect(result.current).toBe('Abbrechen');
    expect(t('common.cancel')).toBe('Abbrechen');
  });

  it('formats numbers and dates in the portal language', () => {
    expect(formatNumber(1234.5)).toBe('1,234.5');
    expect(formatDate('2026-10-29T10:00:00Z')).toBe('29 Oct 2026');
    applyLanguage('de');
    expect(formatNumber(1234.5)).toBe('1.234,5');
    expect(formatDate('2026-10-29T10:00:00Z')).toBe('29. Okt. 2026');
    applyLanguage('fr');
    expect(formatDate('2026-10-29T10:00:00Z')).toBe('29 oct. 2026');
  });
});
