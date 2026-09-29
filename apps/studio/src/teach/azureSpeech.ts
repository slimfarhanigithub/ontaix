/**
 * Azure AI Speech for the teach bar microphone. Each recording asks the API for a short-lived
 * token (`POST /speech/token`), loads the Speech SDK on first use, and runs continuous
 * recognition in the token's language with a phrase list of the active company's labels. Audio
 * goes from the browser straight to the Speech resource. The token is held in memory only and a
 * fresh one is set on the running recogniser before it expires.
 *
 * `startAzureSpeech` resolves null when Azure Speech cannot serve the recording (the API answers
 * 503, the network fails, or the SDK cannot start), and the caller uses the browser's recogniser
 * instead. A refusal the caller must see (403, 409 `channel_disabled`, 429) is thrown as the
 * `ApiError`.
 */
import { api } from '../api/client';
import { ApiError, type SpeechToken } from '../api/types';
import type { SceneState } from '../canvas/state';
import type { Node } from '../canvas/types';

/** Most phrases sent, well under the service's guidance of 2,000. */
export const MAX_PHRASES = 500;
/** Longest label sent as a phrase. */
export const MAX_PHRASE_CHARS = 120;
/** A fresh token is set on the running recogniser this long before the current one expires. */
export const TOKEN_REFRESH_LEAD_MS = 5 * 60_000;
/** Shortest wait before a refresh, so a token already near its expiry is not asked for in a loop. */
const MIN_REFRESH_DELAY_MS = 30_000;

export interface AzureRecording {
  stop(): void;
}

export interface AzureHandlers {
  /** Recognition has started. */
  started(): void;
  /** Words of the current sentence still being recognised. */
  interim(text: string): void;
  /** One finished sentence. */
  final(sentence: string): void;
  /** The recording has ended; `unfinished` holds words the recogniser never finished. */
  ended(unfinished: string): void;
  /** The recogniser stopped with an error; the browser's recogniser takes over the recording. */
  failed(): void;
}

type SpeechSdk = typeof import('microsoft-cognitiveservices-speech-sdk');
type Recognizer = InstanceType<SpeechSdk['SpeechRecognizer']>;

export async function startAzureSpeech(
  companyId: string,
  phrases: string[],
  handlers: AzureHandlers,
): Promise<AzureRecording | null> {
  let token: SpeechToken;
  try {
    token = await api.speechToken(companyId);
  } catch (err) {
    if (err instanceof ApiError && err.status !== 503) throw err;
    return null;
  }
  let sdk: SpeechSdk;
  let recognizer: Recognizer;
  try {
    sdk = await import('microsoft-cognitiveservices-speech-sdk');
    const config = sdk.SpeechConfig.fromAuthorizationToken(token.token, token.region);
    config.speechRecognitionLanguage = token.language;
    recognizer = new sdk.SpeechRecognizer(config, sdk.AudioConfig.fromDefaultMicrophoneInput());
  } catch {
    return null;
  }
  try {
    const grammar = sdk.PhraseListGrammar.fromRecognizer(recognizer);
    for (const phrase of phrases) grammar.addPhrase(phrase);
  } catch {
    recognizer.close();
    return null;
  }
  return run(sdk, recognizer, companyId, token, handlers);
}

/**
 * The phrase list for a recording: the company name, then the labels of the active company's
 * live and pending concepts - those in the focused cell's neighbourhood or the focused domain
 * first, then the most recently born - deduplicated case-insensitively, each at most 120
 * characters, at most 500.
 */
export function speechPhrases(s: SceneState): string[] {
  const company = s.activeCompany;
  if (!company) return [];
  const near = (n: Node) => (s.stickyFocus?.has(n) || (s.focusDomain !== null && n.domain === s.focusDomain) ? 0 : 1);
  const born = (n: Node) => n.bornAt?.getTime() ?? 0;
  const concepts = s.nodes
    .map((n, order) => ({ n, order }))
    .filter(({ n }) => n.kind === 'concept' && n.company === company && !n.dying)
    .sort((a, b) => near(a.n) - near(b.n) || born(b.n) - born(a.n) || b.order - a.order);
  const seen = new Set<string>();
  const phrases: string[] = [];
  for (const label of [company.name, ...concepts.map(({ n }) => n.label)]) {
    const phrase = label.trim();
    const key = phrase.toLowerCase();
    if (!phrase || phrase.length > MAX_PHRASE_CHARS || seen.has(key)) continue;
    seen.add(key);
    phrases.push(phrase);
    if (phrases.length === MAX_PHRASES) break;
  }
  return phrases;
}

function run(
  sdk: SpeechSdk,
  recognizer: Recognizer,
  companyId: string,
  token: SpeechToken,
  handlers: AzureHandlers,
): Promise<AzureRecording | null> {
  let live = false;
  let over = false;
  let unfinished = '';
  let refresh: ReturnType<typeof setTimeout> | undefined;
  let settle: (recording: AzureRecording | null) => void = () => undefined;

  const finish = (failed: boolean) => {
    if (over) return;
    over = true;
    clearTimeout(refresh);
    recognizer.close();
    if (!live) {
      settle(null);
      return;
    }
    handlers.ended(unfinished);
    if (failed) handlers.failed();
  };

  const scheduleRefresh = (expiresAt: string) => {
    const delay = Math.max(MIN_REFRESH_DELAY_MS, Date.parse(expiresAt) - Date.now() - TOKEN_REFRESH_LEAD_MS);
    refresh = setTimeout(() => {
      api.speechToken(companyId).then(
        (next) => {
          if (over) return;
          recognizer.authorizationToken = next.token;
          scheduleRefresh(next.expiresAt);
        },
        // The running token stays until it expires; the recording usually ends long before.
        () => undefined,
      );
    }, delay);
  };

  recognizer.recognizing = (_sender, e) => {
    if (over) return;
    unfinished = e.result.text;
    handlers.interim(unfinished);
  };
  recognizer.recognized = (_sender, e) => {
    if (over || e.result.reason !== sdk.ResultReason.RecognizedSpeech) return;
    unfinished = '';
    const sentence = e.result.text;
    if (sentence.trim()) handlers.final(sentence);
  };
  recognizer.canceled = (_sender, e) => {
    if (e.reason === sdk.CancellationReason.Error) finish(true);
  };
  recognizer.sessionStopped = () => finish(false);

  const recording: AzureRecording = {
    stop() {
      if (over) return;
      recognizer.stopContinuousRecognitionAsync(
        () => finish(false),
        () => finish(false),
      );
    },
  };

  return new Promise((resolve) => {
    settle = resolve;
    recognizer.startContinuousRecognitionAsync(
      () => {
        if (over) return;
        live = true;
        scheduleRefresh(token.expiresAt);
        handlers.started();
        resolve(recording);
      },
      () => finish(false),
    );
  });
}
