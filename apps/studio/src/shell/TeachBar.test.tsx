import { act, cleanup, fireEvent, render } from '@testing-library/react';

import { FakeRecognizer, fakeSpeechSdk, resetFakeRecognizer } from '../teach/speechSdkFake';

type Result = ArrayLike<{ transcript: string }> & { isFinal: boolean };

/** A stand-in for the browser recogniser that the test drives by hand. */
class FakeRecognition {
  static last: FakeRecognition | null = null;
  lang = '';
  interimResults = false;
  continuous = false;
  onstart: (() => void) | null = null;
  onresult: ((ev: { results: ArrayLike<Result> }) => void) | null = null;
  onerror: (() => void) | null = null;
  onend: (() => void) | null = null;
  constructor() {
    FakeRecognition.last = this;
  }
  start(): void {
    this.onstart?.();
  }
  stop(): void {
    this.onend?.();
  }
  /** Delivers the recogniser's whole result list: each entry is final, or still being recognised with `~` in front. */
  hear(...results: string[]): void {
    const list = results.map((t) =>
      Object.assign([{ transcript: t.replace(/^~/, '') }], { isFinal: !t.startsWith('~') }),
    );
    this.onresult?.({ results: list });
  }
}

/** The API has no Speech resource, so each recording falls back to the browser recogniser. */
async function noAzureSpeech(): Promise<void> {
  const { api } = await import('../api/client');
  const { ApiError } = await import('../api/types');
  vi.spyOn(api, 'speechToken').mockRejectedValue(
    new ApiError(503, { title: 'Unavailable', status: 503, code: 'unavailable' }),
  );
}

/** Presses the microphone and lets the token request settle. */
async function click(button: Element): Promise<void> {
  fireEvent.click(button);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

describe('the microphone', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
    (window as unknown as { SpeechRecognition: unknown }).SpeechRecognition = FakeRecognition;
  });
  afterEach(() => {
    vi.useRealTimers();
    delete (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition;
  });

  async function listen() {
    const teachModule = await import('../teach/teach');
    const sentence = vi.fn();
    const stream = vi.spyOn(teachModule, 'speechStream').mockReturnValue({ sentence, settled: () => Promise.resolve() });
    const teach = vi.spyOn(teachModule, 'teach').mockResolvedValue();
    const { TeachBar } = await import('./TeachBar');
    const { container } = render(<TeachBar />);
    fireEvent.click(container.querySelector('#mic') as Element);
    const rec = FakeRecognition.last as FakeRecognition;
    return { container, rec, sentence, stream, teach };
  }

  it('sends each finished sentence at once, as speech, while the speaker goes on', async () => {
    const { rec, sentence, stream, teach } = await listen();
    expect(rec.continuous).toBe(true);

    act(() => rec.hear('~so, uh, Insight sells'));
    expect(sentence).not.toHaveBeenCalled();
    act(() => rec.hear('so, uh, Insight sells services. '));
    expect(sentence.mock.calls).toEqual([['so, uh, Insight sells services. ']]);
    act(() => rec.hear('so, uh, Insight sells services. ', '~These services are'));
    act(() => rec.hear('so, uh, Insight sells services. ', 'These services are focused around three areas, app, data and AI.'));

    expect(sentence.mock.calls).toEqual([
      ['so, uh, Insight sells services. '],
      ['These services are focused around three areas, app, data and AI.'],
    ]);
    expect(stream).toHaveBeenCalledTimes(1);
    expect(teach).not.toHaveBeenCalled();
  });

  it('shows words still being recognised in the input without sending them', async () => {
    const { container, rec, sentence } = await listen();

    act(() => rec.hear('Insight sells services. ', '~These services'));

    expect(sentence.mock.calls).toEqual([['Insight sells services. ']]);
    expect((container.querySelector('#say') as HTMLInputElement).value).toBe('Insight sells services. These services');
  });

  it('sends the words never finished as the last sentence when the speaker stops', async () => {
    const { container, rec, sentence } = await listen();

    act(() => rec.hear('Insight sells services. ', '~These services are focused on data'));
    act(() => {
      vi.advanceTimersByTime(1500);
    });

    expect(sentence.mock.calls).toEqual([['Insight sells services. '], ['These services are focused on data']]);
    expect((container.querySelector('#say') as HTMLInputElement).value).toBe('');
  });

  it('drains the queue on stop, sending the words never finished last, one request at a time', async () => {
    const { api } = await import('../api/client');
    const { store } = await import('../store/store');
    store.s.activeCompany = { sid: 'company-a', name: 'Insight' } as typeof store.s.activeCompany;
    await noAzureSpeech();
    const sent: string[] = [];
    let inFlight = 0;
    let most = 0;
    vi.spyOn(api, 'teachParse').mockImplementation(async (body) => {
      most = Math.max(most, ++inFlight);
      sent.push(body.text as string);
      await new Promise((r) => setTimeout(r, 1000));
      inFlight--;
      return { outcome: 'not_understood', drafts: [], caption: '' } as unknown as Awaited<ReturnType<typeof api.teachParse>>;
    });
    vi.spyOn(store, 'caption').mockImplementation(() => undefined);
    const { TeachBar } = await import('./TeachBar');
    const { container } = render(<TeachBar />);
    await click(container.querySelector('#mic') as Element);
    const rec = FakeRecognition.last as FakeRecognition;

    act(() => rec.hear('Insight sells services. ', 'They focus on data. ', '~It has a platform'));
    act(() => rec.stop());
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(sent).toEqual(['Insight sells services.', 'They focus on data.', 'It has a platform']);
    expect(most).toBe(1);
  });

  it('keeps one request in flight when the speaker stops and starts again during a pending call', async () => {
    const { api } = await import('../api/client');
    const { store } = await import('../store/store');
    store.s.activeCompany = { sid: 'company-a', name: 'Insight' } as typeof store.s.activeCompany;
    await noAzureSpeech();
    const sent: string[] = [];
    let inFlight = 0;
    let most = 0;
    vi.spyOn(api, 'teachParse').mockImplementation(async (body) => {
      most = Math.max(most, ++inFlight);
      sent.push(body.text as string);
      await new Promise((r) => setTimeout(r, 1000));
      inFlight--;
      return { outcome: 'not_understood', drafts: [], caption: '' } as unknown as Awaited<ReturnType<typeof api.teachParse>>;
    });
    vi.spyOn(store, 'caption').mockImplementation(() => undefined);
    const { TeachBar } = await import('./TeachBar');
    const { container } = render(<TeachBar />);
    const micButton = container.querySelector('#mic') as Element;

    await click(micButton);
    act(() => (FakeRecognition.last as FakeRecognition).hear('Insight sells services. '));
    act(() => (FakeRecognition.last as FakeRecognition).stop());
    await click(micButton);
    act(() => (FakeRecognition.last as FakeRecognition).hear('They focus on data. '));
    act(() => (FakeRecognition.last as FakeRecognition).stop());
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(sent).toEqual(['Insight sells services.', 'They focus on data.']);
    expect(most).toBe(1);
  });

  it('stops the recogniser and its silence timer when the teach bar goes away', async () => {
    const { rec, sentence } = await listen();
    const stop = vi.spyOn(rec, 'stop');
    act(() => rec.hear('~Insight sells'));

    cleanup();
    vi.advanceTimersByTime(1500);

    expect(stop).toHaveBeenCalledTimes(1);
    expect(sentence).toHaveBeenCalledTimes(1);
  });
});

describe('the microphone on Azure Speech', () => {
  const TOKEN = {
    token: 'aad#/subscriptions/s#eyJ.token',
    region: 'francecentral',
    expiresAt: '2099-01-01T00:00:00Z',
    language: 'en-GB' as const,
  };

  beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
    vi.doMock('microsoft-cognitiveservices-speech-sdk', () => fakeSpeechSdk());
    (window as unknown as { SpeechRecognition: unknown }).SpeechRecognition = FakeRecognition;
    FakeRecognition.last = null;
    resetFakeRecognizer();
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.doUnmock('microsoft-cognitiveservices-speech-sdk');
    delete (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition;
  });

  async function listen(token: () => Promise<typeof TOKEN>) {
    const { api } = await import('../api/client');
    const { store } = await import('../store/store');
    store.s.activeCompany = { sid: 'company-a', name: 'Insight' } as typeof store.s.activeCompany;
    vi.spyOn(api, 'speechToken').mockImplementation(token);
    const refused = vi.spyOn(store, 'refused').mockImplementation(() => undefined);
    const teachModule = await import('../teach/teach');
    const sentence = vi.fn();
    vi.spyOn(teachModule, 'speechStream').mockReturnValue({ sentence, settled: () => Promise.resolve() });
    const { TeachBar } = await import('./TeachBar');
    const { container } = render(<TeachBar />);
    await click(container.querySelector('#mic') as Element);
    const input = () => (container.querySelector('#say') as HTMLInputElement).value;
    return { container, input, refused, sentence };
  }

  it('queues each recognised sentence and shows words being recognised only in the input', async () => {
    const { input, sentence } = await listen(() => Promise.resolve(TOKEN));
    const rec = FakeRecognizer.last as FakeRecognizer;
    expect(rec.phrases).toEqual(['Insight']);
    expect(FakeRecognition.last).toBeNull();

    act(() => rec.hearing('so, uh, Insight sells'));
    expect(sentence).not.toHaveBeenCalled();
    expect(input()).toBe('so, uh, Insight sells');
    act(() => rec.heard('So, uh, Insight sells services.'));
    act(() => rec.hearing('These services are'));

    expect(sentence.mock.calls).toEqual([['So, uh, Insight sells services.']]);
    expect(input()).toBe('So, uh, Insight sells services. These services are');
  });

  it('sends the words never finished as the last sentence when the speaker stops', async () => {
    const { input, sentence } = await listen(() => Promise.resolve(TOKEN));
    const rec = FakeRecognizer.last as FakeRecognizer;

    act(() => rec.heard('Insight sells services.'));
    act(() => rec.hearing('These services are focused on data'));
    act(() => {
      vi.advanceTimersByTime(1500);
    });

    expect(sentence.mock.calls).toEqual([['Insight sells services.'], ['These services are focused on data']]);
    expect(rec.closed).toBe(true);
    expect(input()).toBe('');
  });

  it('falls back to the browser recogniser on 503, as it does without Azure Speech', async () => {
    const { ApiError } = await import('../api/types');
    const unavailable = new ApiError(503, { title: 'Unavailable', status: 503, code: 'unavailable' });
    const { sentence } = await listen(() => Promise.reject(unavailable));
    const rec = FakeRecognition.last as FakeRecognition;

    act(() => rec.hear('Insight sells services. '));

    expect(FakeRecognizer.last).toBeNull();
    expect(rec.continuous).toBe(true);
    expect(sentence.mock.calls).toEqual([['Insight sells services. ']]);
  });

  it('hands the recording to the browser recogniser when Azure Speech cancels with an error', async () => {
    const { sentence } = await listen(() => Promise.resolve(TOKEN));

    act(() => (FakeRecognizer.last as FakeRecognizer).fail());
    act(() => (FakeRecognition.last as FakeRecognition).hear('Insight sells services. '));

    expect(sentence.mock.calls).toEqual([['Insight sells services. ']]);
  });

  it('shows a refusal and does not fall back when voice is off', async () => {
    const { ApiError } = await import('../api/types');
    const off = new ApiError(409, { title: 'Channel disabled', status: 409, code: 'channel_disabled' });
    const { refused } = await listen(() => Promise.reject(off));

    expect(refused).toHaveBeenCalledWith(off);
    expect(FakeRecognition.last).toBeNull();
  });
});
