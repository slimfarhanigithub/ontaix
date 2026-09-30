/**
 * The teach bar: company selector, sentence input, microphone and Teach. Markup from
 * reference/ontaix-studio-reference.html lines 202-208 without the Next button; behaviours from
 * lines 610-611, 885-886 and 1091-1095 (voice). Typed sentences are taught as `text`. The
 * microphone listens until the speaker stops (a pause, or a second press) and queues each sentence
 * the recogniser finishes as `speech` while the speaker goes on, so cells appear during speech;
 * words still being recognised only show in the input. The microphone is a toggle (`aria-pressed`):
 * pressed again, or after a pause, it stops at once and the words never finished join the queue as
 * the last sentence, which drains.
 *
 * The bar is one line: the caption as a disclosure button, the company selector, the input, the
 * Processing status, the microphone and Teach. Opened, it grows upward with the last captions and
 * the whole current sentence in a text area of up to five lines; Escape closes it and gives focus
 * back to the disclosure button. Whether it is open is remembered per browser. A typed sentence
 * stays in the input until its parse answers: it clears once taught, and when the model did not
 * understand it or the API refused it, it is put back, selected, to be fixed.
 *
 * Recognition runs on Azure AI Speech (../teach/azureSpeech) with the company's labels as a
 * phrase list; when the API has no Speech resource, the network fails or the SDK cannot run, the
 * recording uses the browser's recogniser instead. Both show and queue words the same way.
 */
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react';

import { ApiError } from '../api/types';
import { speechPhrases, startAzureSpeech } from '../teach/azureSpeech';
import { speechStream, teach } from '../teach/teach';
import { Caption } from './Caption';
import { useStore } from './dom';
import { readExpanded, writeExpanded } from './teachBarState';
import { TeachLog } from './TeachLog';
import { TeachStatus } from './TeachStatus';

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onstart: (() => void) | null;
  onresult: ((ev: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

/** Silence after the last recognised words that ends a recording. */
const SILENCE_MS = 1500;
/** Silence at the start of an Azure recording that ends it; the browser's recogniser ends itself. */
const NO_SPEECH_MS = 8000;
/** Lines the open bar's text area grows to before it scrolls. */
const MAX_LINES = 5;

interface Recording {
  stop(): void;
}

/** The recording in progress: `end` stops it and queues the words not finished yet at once. */
interface Live {
  end(): void;
}

const SR: SpeechRecognitionCtor | undefined =
  (window as unknown as { SpeechRecognition?: SpeechRecognitionCtor }).SpeechRecognition ||
  (window as unknown as { webkitSpeechRecognition?: SpeechRecognitionCtor }).webkitSpeechRecognition;

export function TeachBar() {
  const st = useStore();
  const { say, sayPlaceholder, settings, listening } = st.ui;
  const companies = st.s.companies;
  const recording = useRef<Recording | null>(null);
  /** Ends the current recording and queues its unfinished words; null while nothing records. */
  const live = useRef<Live | null>(null);
  const starting = useRef(false);
  /** Set when the microphone is pressed again while an Azure recording is still starting. */
  const cancelStart = useRef(false);
  const mounted = useRef(true);
  const [errorPlaceholder, setErrorPlaceholder] = useState<string | null>(null);
  const mic = useRef<HTMLButtonElement>(null);
  const silence = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [expanded, setExpanded] = useState(readExpanded);
  const [heard, setHeard] = useState('');
  const form = useRef<HTMLFormElement>(null);
  const more = useRef<HTMLButtonElement>(null);
  const field = useRef<HTMLInputElement & HTMLTextAreaElement>(null);
  /** Typed sentences whose parse has not answered yet. */
  const pending = useRef(new Set<string>());
  /** Bumped to select the input's text once it is rendered. */
  const [selectSeq, setSelectSeq] = useState(0);

  const toggle = () => {
    writeExpanded(!expanded);
    setExpanded(!expanded);
  };

  // The tools row sits above the bar and follows its height through --teach-h.
  useEffect(() => {
    const el = form.current;
    if (!el) return;
    const measure = () => document.documentElement.style.setProperty('--teach-h', `${el.offsetHeight}px`);
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // The open bar's text area grows with its text up to MAX_LINES, then scrolls.
  useLayoutEffect(() => {
    const el = field.current;
    if (!el || el.tagName !== 'TEXTAREA') return;
    const css = getComputedStyle(el);
    const line = parseFloat(css.lineHeight) || 21;
    const pad = (parseFloat(css.paddingTop) || 0) + (parseFloat(css.paddingBottom) || 0);
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, line * MAX_LINES + pad)}px`;
  }, [say, expanded]);

  // A sentence put back after a failed teach is selected, ready to be fixed.
  useEffect(() => {
    if (!selectSeq) return;
    field.current?.focus();
    field.current?.select();
  }, [selectSeq]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearTimeout(silence.current);
      if (live.current) live.current.end();
      else recording.current?.stop();
    };
  }, []);

  useEffect(() => {
    const el = mic.current;
    if (el && !SR) {
      el.title = 'Voice input is not available in this browser';
      el.style.opacity = '.4';
    }
  }, []);

  /**
   * The microphone is a toggle. The first press starts listening; the second stops the recogniser
   * and sends the words still being recognised at once, as the last sentence of the queue, without
   * waiting for the recogniser to finish them.
   */
  const speak = () => {
    if (live.current) {
      live.current.end();
      return;
    }
    if (starting.current) {
      cancelStart.current = true;
      return;
    }
    const companyId = st.s.activeCompany?.sid;
    if (companyId) listenWithAzure(companyId);
    else listenInBrowser();
  };

  /**
   * One recording's end, shared by both recognisers: the first call queues `unfinished()` (the
   * words not finished yet), clears the input when words were heard, marks the bar idle and stops
   * the recogniser; later calls and results that arrive after it change nothing.
   */
  const recordingEnd = (stream: ReturnType<typeof speechStream>, unfinished: () => string, heard: () => boolean, stop: () => void) => {
    let over = false;
    return {
      get over() {
        return over;
      },
      end() {
        if (over) return;
        over = true;
        clearTimeout(silence.current);
        live.current = null;
        const words = unfinished();
        if (words.trim()) stream.sentence(words);
        if (heard()) st.setSay('');
        st.ui.listening = false;
        st.bump();
        stop();
      },
    };
  };

  const listenWithAzure = (companyId: string) => {
    const stream = speechStream();
    // Sentences of this recording already finished and queued, as the input shows them.
    let done = '';
    let heard = false;
    // Words still being recognised, sent as the last sentence when the recording ends.
    let pending = '';
    // This recording once Azure Speech has started it; a newer recording may replace it in `recording`.
    let mine: Recording | null = null;
    const rec = recordingEnd(
      stream,
      () => pending,
      () => heard,
      () => mine?.stop(),
    );
    const quiet = (ms: number) => {
      clearTimeout(silence.current);
      silence.current = setTimeout(() => rec.end(), ms);
    };
    starting.current = true;
    cancelStart.current = false;
    startAzureSpeech(companyId, speechPhrases(st.s), {
      started() {
        if (cancelStart.current) return;
        setHeard('');
        live.current = rec;
        st.ui.listening = true;
        st.bump();
        quiet(NO_SPEECH_MS);
      },
      interim(text) {
        if (rec.over) return;
        heard = true;
        pending = text;
        st.setSay(done + text);
        quiet(SILENCE_MS);
      },
      final(sentence) {
        if (rec.over) return;
        heard = true;
        pending = '';
        stream.sentence(sentence);
        setHeard(sentence.trim());
        done += `${sentence} `;
        st.setSay(done);
        quiet(SILENCE_MS);
      },
      ended(unfinished) {
        if (recording.current === mine) recording.current = null;
        if (!rec.over) pending = unfinished;
        rec.end();
      },
      failed: listenInBrowser,
    }).then(
      (r) => {
        starting.current = false;
        if (!r) {
          listenInBrowser();
          return;
        }
        mine = r;
        recording.current = r;
        if (rec.over) r.stop();
        else if (!mounted.current || cancelStart.current) {
          cancelStart.current = false;
          rec.end();
        }
      },
      (err) => {
        starting.current = false;
        cancelStart.current = false;
        if (err instanceof ApiError) st.refused(err);
        else listenInBrowser();
      },
    );
  };

  const listenInBrowser = () => {
    if (!SR || !mounted.current) return;
    const r = new SR();
    recording.current = r;
    r.lang = /^fr/i.test(navigator.language) ? 'fr-FR' : 'en-GB';
    r.interimResults = true;
    r.continuous = true;
    const stream = speechStream();
    // Results before this index are final and already sent; the rest are still being recognised.
    let finished = 0;
    let pending = '';
    let heard = false;
    let ended = false;
    const rec = recordingEnd(
      stream,
      () => pending,
      () => heard,
      () => {
        if (!ended) r.stop();
      },
    );
    r.onstart = () => {
      setHeard('');
      live.current = rec;
      st.ui.listening = true;
      st.bump();
    };
    r.onresult = (ev) => {
      if (rec.over) return;
      let s = '';
      pending = '';
      for (let i = 0; i < ev.results.length; i++) {
        const words = ev.results[i][0].transcript;
        s += words;
        if (i < finished) continue;
        if (ev.results[i].isFinal && i === finished) {
          stream.sentence(words);
          setHeard(words.trim());
          finished++;
        } else pending += words;
      }
      heard = true;
      st.setSay(s);
      clearTimeout(silence.current);
      silence.current = setTimeout(() => rec.end(), SILENCE_MS);
    };
    r.onerror = () => {
      setErrorPlaceholder('The microphone did not respond. Type instead, the show goes on.');
    };
    r.onend = () => {
      ended = true;
      if (recording.current === r) recording.current = null;
      rec.end();
    };
    r.start();
  };

  /** Teaches the typed sentence; it leaves the input once taught and comes back, selected, when not. */
  const submit = async (text: string) => {
    if (!text.trim() || pending.current.has(text)) return;
    pending.current.add(text);
    let taught: boolean | void;
    try {
      taught = await teach(text, 'text');
    } finally {
      pending.current.delete(text);
    }
    if (!mounted.current) return;
    const now = st.ui.say;
    if (taught === false) {
      if (now !== text && now.trim()) return;
      st.setSay(text);
      setSelectSeq((n) => n + 1);
    } else if (now === text) st.setSay('');
  };

  /** Escape closes the open bar, hands focus back to the disclosure button and goes no further. */
  const onKeyDown = (e: KeyboardEvent<HTMLFormElement>) => {
    if (e.key !== 'Escape' || !expanded) return;
    e.preventDefault();
    e.stopPropagation();
    writeExpanded(false);
    setExpanded(false);
    more.current?.focus();
  };

  const liveTeaching = !settings || settings.liveTeaching;
  const placeholder = !liveTeaching ? 'Live teaching is disabled in the admin portal' : errorPlaceholder || sayPlaceholder;

  const fieldProps = {
    id: 'say',
    ref: field,
    placeholder,
    'aria-label': 'Teach the model',
    value: say,
    disabled: !liveTeaching,
    onChange: (e: { target: { value: string } }) => st.setSay(e.target.value),
  };

  return (
    <form
      className={`bar${expanded ? ' open' : ''}`}
      id="bar-form"
      autoComplete="off"
      ref={form}
      onKeyDown={onKeyDown}
      onSubmit={(e) => {
        e.preventDefault();
        void submit(say);
      }}
    >
      <Caption expanded={expanded} onToggle={toggle} heard={heard} buttonRef={more} />
      <span className="sep" aria-hidden="true"></span>
      <select
        id="companySel"
        aria-label="Company being taught"
        title="Which company you are teaching"
        style={{ display: companies.length > 1 ? undefined : 'none' }}
        value={st.s.activeCompany?.key ?? ''}
        onChange={(e) => st.selectCompany(e.target.value)}
      >
        {companies.map((c) => (
          <option key={c.key} value={c.key}>
            {c.name}
          </option>
        ))}
      </select>
      {expanded ? (
        <textarea
          {...fieldProps}
          rows={1}
          readOnly={listening}
          onKeyDown={(e) => {
            if (e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing) return;
            e.preventDefault();
            form.current?.requestSubmit();
          }}
        />
      ) : (
        <input {...fieldProps} type="text" />
      )}
      <TeachStatus />
      <button
        type="button"
        className={`mic${listening ? ' on' : ''}`}
        id="mic"
        aria-label="Speak"
        aria-pressed={listening}
        title={listening ? 'Stop listening and teach what was heard' : 'Speak: press again to stop and teach'}
        ref={mic}
        style={{ display: settings && !settings.voice ? 'none' : undefined }}
        onClick={speak}
      >
        {listening ? (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
          </svg>
        )}
      </button>
      <button type="submit" id="teach">
        Teach
      </button>
      <TeachLog expanded={expanded} />
    </form>
  );
}
