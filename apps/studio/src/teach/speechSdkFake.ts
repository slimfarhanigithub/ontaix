/**
 * A stand-in for the Azure Speech SDK that tests drive by hand, installed with
 * `vi.doMock('microsoft-cognitiveservices-speech-sdk', () => fakeSpeechSdk())`.
 */

export const RECOGNIZED_SPEECH = 3;
export const CANCELLED_WITH_ERROR = 1;

interface FakeConfig {
  token: string;
  region: string;
  speechRecognitionLanguage: string;
}

type Handler = ((sender: unknown, e: never) => void) | null;

export class FakeRecognizer {
  static last: FakeRecognizer | null = null;
  /** When set, the next recogniser fails to start. */
  static failStart = false;
  recognizing: Handler = null;
  recognized: Handler = null;
  canceled: Handler = null;
  sessionStopped: Handler = null;
  authorizationToken = '';
  phrases: string[] = [];
  started = false;
  closed = false;
  constructor(public readonly config: FakeConfig) {
    FakeRecognizer.last = this;
  }
  startContinuousRecognitionAsync(cb?: () => void, err?: (e: string) => void): void {
    if (FakeRecognizer.failStart) {
      err?.('connection failed');
      return;
    }
    this.started = true;
    cb?.();
  }
  stopContinuousRecognitionAsync(cb?: () => void): void {
    this.started = false;
    cb?.();
  }
  close(): void {
    this.closed = true;
  }
  /** Words still being recognised. */
  hearing(text: string): void {
    this.recognizing?.(this, { result: { text } } as never);
  }
  /** A finished sentence. */
  heard(text: string): void {
    this.recognized?.(this, { result: { text, reason: RECOGNIZED_SPEECH } } as never);
  }
  /** The service cancels the recognition with an error. */
  fail(): void {
    this.canceled?.(this, { reason: CANCELLED_WITH_ERROR } as never);
  }
}

/** Forgets the last recogniser and lets the next one start. */
export function resetFakeRecognizer(): void {
  FakeRecognizer.last = null;
  FakeRecognizer.failStart = false;
}

export function fakeSpeechSdk() {
  return {
    SpeechConfig: {
      fromAuthorizationToken: (token: string, region: string): FakeConfig => ({
        token,
        region,
        speechRecognitionLanguage: '',
      }),
    },
    AudioConfig: { fromDefaultMicrophoneInput: () => ({}) },
    SpeechRecognizer: FakeRecognizer,
    PhraseListGrammar: {
      fromRecognizer: (r: FakeRecognizer) => ({ addPhrase: (p: string) => r.phrases.push(p) }),
    },
    ResultReason: { RecognizedSpeech: RECOGNIZED_SPEECH },
    CancellationReason: { Error: CANCELLED_WITH_ERROR },
  };
}
