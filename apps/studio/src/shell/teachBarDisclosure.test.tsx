import { act, cleanup, fireEvent, render } from '@testing-library/react';

import { api } from '../api/client';
import { ApiError, type TeachResult } from '../api/types';
import { store } from '../store/store';
import { TeachBar } from './TeachBar';
import { EXPANDED_KEY } from './teachBarState';

/** A promise with its resolve and reject in hand. */
function deferred<T = void>() {
  let resolve!: (v: T) => void, reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const result = (outcome: TeachResult['outcome'], caption: string): TeachResult =>
  ({ outcome, domainKey: null, intents: [], drafts: [], statements: [], caption, origin: 'text' }) as unknown as TeachResult;

const $ = <T extends Element = HTMLElement>(c: HTMLElement, sel: string) => c.querySelector(sel) as unknown as T;

let before: typeof store.s.activeCompany;
beforeEach(() => {
  localStorage.clear();
  before = store.s.activeCompany;
  store.s.activeCompany = { sid: 'company-a', name: 'Insight' } as typeof before;
  store.ui.history = [];
  store.ui.say = '';
  store.ui.listening = false;
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  store.s.activeCompany = before;
  store.ui.history = [];
  store.ui.say = '';
  store.ui.toasts = [];
});

describe('teach bar disclosure', () => {
  it('starts collapsed with the latest caption on one line, and opens to the history and a text area', () => {
    act(() => {
      for (let i = 1; i <= 7; i++) store.caption(`Understood ${i}`, `Caption number ${i}`);
    });
    const { container } = render(<TeachBar />);
    const more = $(container, '#teachMore');
    expect(more.getAttribute('aria-expanded')).toBe('false');
    expect(more.getAttribute('aria-controls')).toBe('teachLog');
    expect($(container, '#captionKicker').textContent).toBe('Understood 7');
    expect(more.title).toBe('Understood 7 Caption number 7');
    expect($(container, '#teachLog').hidden).toBe(true);
    expect($(container, '#say').tagName).toBe('INPUT');

    fireEvent.click(more);
    expect(more.getAttribute('aria-expanded')).toBe('true');
    expect($(container, 'form.bar').classList.contains('open')).toBe(true);
    const log = $(container, '#teachLog');
    expect(log.hidden).toBe(false);
    expect(log.getAttribute('role')).toBe('log');
    expect(Array.from(log.querySelectorAll('div b')).map((b) => b.textContent)).toEqual([
      'Understood 3',
      'Understood 4',
      'Understood 5',
      'Understood 6',
      'Understood 7',
    ]);
    expect($(container, '#say').tagName).toBe('TEXTAREA');

    fireEvent.click(more);
    expect(more.getAttribute('aria-expanded')).toBe('false');
    expect($(container, '#teachLog').hidden).toBe(true);
  });

  it('merges identical consecutive captions and copies refusals into the history', () => {
    act(() => {
      store.caption('Approved', 'Pump is part of Production.');
      store.caption('Approved', 'Pump is part of Production.');
      store.refused(new ApiError(403, { title: 'Forbidden', status: 403, code: 'forbidden', detail: 'Only a Governor can approve' }));
    });
    expect(store.ui.history.map((h) => [h.kicker, h.refused])).toEqual([
      ['Approved', false],
      ['Refused', true],
    ]);
    const { container } = render(<TeachBar />);
    expect($(container, '#teachMore').classList.contains('refused')).toBe(true);
  });

  it('remembers whether it is open, and survives storage that refuses access', () => {
    const first = render(<TeachBar />);
    fireEvent.click($(first.container, '#teachMore'));
    expect(localStorage.getItem(EXPANDED_KEY)).toBe('1');
    first.unmount();

    const second = render(<TeachBar />);
    expect($(second.container, '#teachMore').getAttribute('aria-expanded')).toBe('true');
    fireEvent.click($(second.container, '#teachMore'));
    expect(localStorage.getItem(EXPANDED_KEY)).toBe('0');
    second.unmount();

    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    const third = render(<TeachBar />);
    const more = $(third.container, '#teachMore');
    expect(more.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(more);
    expect(more.getAttribute('aria-expanded')).toBe('true');
  });

  it('closes on Escape, gives focus back to the disclosure button and keeps Escape from the canvas', () => {
    localStorage.setItem(EXPANDED_KEY, '1');
    const escape = vi.spyOn(store, 'escape');
    const onWindow = vi.fn();
    addEventListener('keydown', onWindow);
    const { container } = render(<TeachBar />);
    const say = $(container, '#say');
    say.focus();
    fireEvent.keyDown(say, { key: 'Escape' });
    removeEventListener('keydown', onWindow);
    const more = $(container, '#teachMore');
    expect(more.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(more);
    expect(onWindow).not.toHaveBeenCalled();
    expect(escape).not.toHaveBeenCalled();
    expect(localStorage.getItem(EXPANDED_KEY)).toBe('0');
  });

  it('teaches on Enter in the open text area and starts a new line with Shift+Enter', async () => {
    localStorage.setItem(EXPANDED_KEY, '1');
    const teach = vi.spyOn(api, 'teachParse').mockResolvedValue(result('understood', 'ok'));
    const { container } = render(<TeachBar />);
    const say = $<HTMLTextAreaElement>(container, '#say');
    fireEvent.change(say, { target: { value: 'Insight sells services' } });
    fireEvent.keyDown(say, { key: 'Enter', shiftKey: true });
    expect(teach).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.keyDown(say, { key: 'Enter' });
    });
    expect(teach).toHaveBeenCalledTimes(1);
    expect(teach.mock.calls[0][0].text).toBe('Insight sells services');
  });

  it('shows Listening and the last finished words while the microphone listens', () => {
    const { container, rerender } = render(<TeachBar />);
    act(() => {
      store.ui.listening = true;
      store.bump();
    });
    rerender(<TeachBar />);
    expect($(container, '#captionKicker').textContent).toBe('Listening');
    expect($(container, '#captionKicker .dot')).not.toBeNull();
  });
});

describe('the typed sentence', () => {
  it('stays in the input while it is parsed and clears once taught', async () => {
    const parsed = deferred<TeachResult>();
    vi.spyOn(api, 'teachParse').mockReturnValue(parsed.promise);
    const { container } = render(<TeachBar />);
    const say = $<HTMLInputElement>(container, '#say');
    fireEvent.change(say, { target: { value: 'Insight sells services' } });
    fireEvent.submit($(container, 'form.bar'));
    expect(say.value).toBe('Insight sells services');
    await act(async () => parsed.resolve(result('understood', 'Insight sells Service.')));
    expect(say.value).toBe('');
  });

  it('comes back selected when the model did not understand it', async () => {
    const parsed = deferred<TeachResult>();
    vi.spyOn(api, 'teachParse').mockReturnValue(parsed.promise);
    const { container } = render(<TeachBar />);
    const say = $<HTMLInputElement>(container, '#say');
    fireEvent.change(say, { target: { value: 'purple elephants dance' } });
    fireEvent.submit($(container, 'form.bar'));
    fireEvent.change(say, { target: { value: '' } });
    await act(async () => parsed.resolve(result('not_understood', 'Try "A is a B".')));
    expect(say.value).toBe('purple elephants dance');
    expect(document.activeElement).toBe(say);
    expect([say.selectionStart, say.selectionEnd]).toEqual([0, 'purple elephants dance'.length]);
    expect($(container, '#captionKicker').textContent).toBe('Not understood');
    expect($(container, '#teachMore').classList.contains('refused')).toBe(true);
  });

  it('comes back selected when the API refuses the parse', async () => {
    vi.spyOn(api, 'teachParse').mockRejectedValue(new ApiError(503, { title: 'busy', status: 503, code: 'busy', detail: 'Try later' }));
    const { container } = render(<TeachBar />);
    const say = $<HTMLInputElement>(container, '#say');
    fireEvent.change(say, { target: { value: 'Insight sells services' } });
    await act(async () => {
      fireEvent.submit($(container, 'form.bar'));
    });
    expect(say.value).toBe('Insight sells services');
    expect([say.selectionStart, say.selectionEnd]).toEqual([0, 'Insight sells services'.length]);
    expect(store.ui.toasts.map((t) => t.strong)).toContain('Refused');
  });

  it('leaves a newer sentence alone when an earlier one fails', async () => {
    const parsed = deferred<TeachResult>();
    vi.spyOn(api, 'teachParse').mockReturnValue(parsed.promise);
    const { container } = render(<TeachBar />);
    const say = $<HTMLInputElement>(container, '#say');
    fireEvent.change(say, { target: { value: 'first sentence' } });
    fireEvent.submit($(container, 'form.bar'));
    fireEvent.change(say, { target: { value: 'second sentence' } });
    await act(async () => parsed.resolve(result('not_understood', 'hint')));
    expect(say.value).toBe('second sentence');
  });

  it('is sent once while its parse is pending', async () => {
    const parsed = deferred<TeachResult>();
    const teach = vi.spyOn(api, 'teachParse').mockReturnValue(parsed.promise);
    const { container } = render(<TeachBar />);
    fireEvent.change($(container, '#say'), { target: { value: 'Insight sells services' } });
    fireEvent.submit($(container, 'form.bar'));
    fireEvent.submit($(container, 'form.bar'));
    expect(teach).toHaveBeenCalledTimes(1);
    await act(async () => parsed.resolve(result('understood', 'ok')));
  });
});
