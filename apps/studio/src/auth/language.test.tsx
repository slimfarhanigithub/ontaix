import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

import { applyLanguage, LANGUAGE_KEY, languageStore } from '../i18n/language';
import { AccountControls } from './AccountControls';
import { auth } from './authStore';
import { json, session, stubFetch } from './fetchStub';

const flush = () => act(() => new Promise((r) => setTimeout(r, 0)));

const account = (language: 'en' | 'fr' | 'de' | null) => ({ id: 'acc-1', email: 'ana@acme.example', name: 'Ana', language });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  act(() => applyLanguage('en'));
  localStorage.clear();
});

describe('the account menu language choice', () => {
  it('switches the portal at once, saves the choice on the session and in the browser', async () => {
    const stub = stubFetch({
      'PUT /auth/session/language': (call) => json(200, session({ account: account((call.body as { language: 'fr' }).language) })),
    });
    auth.replaceSession(session({ account: account(null) }));
    render(<AccountControls />);
    expect(screen.getByRole('button', { name: 'Change password' })).toBeInTheDocument();
    const button = screen.getByRole('button', { name: 'Language' });
    expect(button).toHaveClass('btn');
    expect(button).toHaveAttribute('aria-haspopup', 'menu');
    fireEvent.click(button);
    expect(screen.getByRole('menu', { name: 'Language' })).toBeInTheDocument();
    const items = screen.getAllByRole('menuitemradio');
    expect(items.map((i) => i.textContent)).toEqual(['English', 'Français', 'Deutsch']);
    expect(items.map((i) => i.getAttribute('aria-checked'))).toEqual(['true', 'false', 'false']);
    expect(items[1]).toHaveAttribute('lang', 'fr');
    fireEvent.click(items[1]);
    expect(languageStore.language).toBe('fr');
    expect(document.documentElement.lang).toBe('fr');
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe('fr');
    expect(screen.getByRole('button', { name: 'Changer le mot de passe' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Langue' })).toBeInTheDocument();
    await flush();
    const calls = stub.to('PUT /auth/session/language');
    expect(calls).toHaveLength(1);
    expect(calls[0].body).toEqual({ language: 'fr' });
    expect(auth.state.session?.account.language).toBe('fr');
  });

  it('opens in the account language when a session comes in', () => {
    auth.replaceSession(session({ account: account('de') }));
    expect(languageStore.language).toBe('de');
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe('de');
    auth.replaceSession(session({ account: account(null) }));
    expect(languageStore.language).toBe('en');
  });
});
