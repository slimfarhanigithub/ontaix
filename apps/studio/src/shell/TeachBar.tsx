/**
 * The teach bar: company selector, sentence input, microphone and Teach. Markup from
 * reference/ontaix-studio-reference.html lines 202-208 without the Next button; behaviours from
 * lines 610-611, 885-886 and 1091-1095 (voice). Typed sentences are taught as `text`, the
 * microphone's final transcript as `speech`.
 */
import { useEffect, useRef, useState } from 'react';

import type { InputOrigin } from '../api/types';
import { teach } from '../teach/teach';
import { useStore } from './dom';

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

const SR: SpeechRecognitionCtor | undefined =
  (window as unknown as { SpeechRecognition?: SpeechRecognitionCtor }).SpeechRecognition ||
  (window as unknown as { webkitSpeechRecognition?: SpeechRecognitionCtor }).webkitSpeechRecognition;

export function TeachBar() {
  const st = useStore();
  const { say, sayPlaceholder, settings, listening } = st.ui;
  const companies = st.s.companies;
  const rec = useRef<SpeechRecognitionLike | null>(null);
  const [errorPlaceholder, setErrorPlaceholder] = useState<string | null>(null);
  const mic = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const el = mic.current;
    if (el && !SR) {
      el.title = 'Voice input is not available in this browser';
      el.style.opacity = '.4';
    }
  }, []);

  const speak = () => {
    if (!SR) return;
    if (listening) {
      rec.current?.stop();
      return;
    }
    const r = new SR();
    rec.current = r;
    r.lang = /^fr/i.test(navigator.language) ? 'fr-FR' : 'en-GB';
    r.interimResults = true;
    r.continuous = false;
    r.onstart = () => {
      st.ui.listening = true;
      st.bump();
    };
    r.onresult = (ev) => {
      let s = '';
      for (let i = 0; i < ev.results.length; i++) s += ev.results[i][0].transcript;
      st.setSay(s);
      if (ev.results[ev.results.length - 1].isFinal) {
        submit(s, 'speech');
        st.setSay('');
      }
    };
    r.onerror = () => {
      setErrorPlaceholder('The microphone did not respond. Type instead, the show goes on.');
    };
    r.onend = () => {
      st.ui.listening = false;
      st.bump();
    };
    r.start();
  };

  const submit = (text: string, origin: InputOrigin) => {
    void teach(text, origin);
  };

  const liveTeaching = !settings || settings.liveTeaching;
  const placeholder = !liveTeaching ? 'Live teaching is disabled in the admin portal' : errorPlaceholder || sayPlaceholder;

  return (
    <form
      className="bar"
      id="bar-form"
      autoComplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        submit(say, 'text');
        st.setSay('');
      }}
    >
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
      <input
        id="say"
        type="text"
        placeholder={placeholder}
        aria-label="Teach the model"
        value={say}
        disabled={!liveTeaching}
        onChange={(e) => st.setSay(e.target.value)}
      />
      <button
        type="button"
        className={`mic${listening ? ' on' : ''}`}
        id="mic"
        aria-label="Speak"
        title="Speak"
        ref={mic}
        style={{ display: settings && !settings.voice ? 'none' : undefined }}
        onClick={speak}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
        </svg>
      </button>
      <button type="submit" id="teach">
        Teach
      </button>
    </form>
  );
}
