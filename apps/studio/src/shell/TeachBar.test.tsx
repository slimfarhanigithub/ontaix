import { act, fireEvent, render } from '@testing-library/react';

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
  hear(...finals: string[]): void {
    const results = finals.map((t) => Object.assign([{ transcript: t }], { isFinal: true }));
    this.onresult?.({ results });
  }
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

  it('sends the whole transcript once, as speech, when the speaker stops', async () => {
    const teachModule = await import('../teach/teach');
    const teach = vi.spyOn(teachModule, 'teach').mockResolvedValue();
    const { TeachBar } = await import('./TeachBar');
    const { container } = render(<TeachBar />);

    fireEvent.click(container.querySelector('#mic') as Element);
    const rec = FakeRecognition.last as FakeRecognition;
    expect(rec.continuous).toBe(true);
    act(() => rec.hear('so, uh, Insight sells services. '));
    act(() => rec.hear('so, uh, Insight sells services. ', 'These services are focused around three areas, app, data and AI.'));
    expect(teach).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1500);
    });

    expect(teach).toHaveBeenCalledTimes(1);
    expect(teach).toHaveBeenCalledWith(
      'so, uh, Insight sells services. These services are focused around three areas, app, data and AI.',
      'speech',
    );
  });
});
