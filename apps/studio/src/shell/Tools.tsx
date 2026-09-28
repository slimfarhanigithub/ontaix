/**
 * The tool row above the teach bar. Markup from reference/ontaix-studio-reference.html lines
 * 194-201; behaviours from lines 548-565 (arrange, coverage, finalise, skip).
 */
import { useRef } from 'react';

import { finaliseAll } from '../demo/story';
import { useStore } from './dom';

export function Tools() {
  const st = useStore();
  const settings = st.ui.settings;
  const file = useRef<HTMLInputElement>(null);
  return (
    <div className="tools" id="tools">
      <button
        type="button"
        id="addCo"
        title="Add another company to the same view"
        style={{ display: settings && !settings.multiCompany ? 'none' : undefined }}
      >
        <svg viewBox="0 0 16 16">
          <path d="M8 3v10M3 8h10" />
        </svg>
        Company
      </button>
      <button
        type="button"
        id="importBtn"
        title="Import a document and detect concepts and relations (I)"
        style={{ display: settings && !settings.importDocs ? 'none' : undefined }}
        onClick={() => file.current?.click()}
      >
        <svg viewBox="0 0 16 16">
          <path d="M8 2v8M4.5 6.5 8 10l3.5-3.5M3 13h10" />
        </svg>
        Import
      </button>
      <input
        type="file"
        id="importFile"
        accept=".txt,.md,.csv,.json,.docx,.pdf"
        hidden
        ref={file}
        onChange={(e) => {
          e.currentTarget.value = '';
        }}
      />
      <button type="button" id="arrange" title={st.arrangeTitle()} onClick={() => st.arrange()}>
        <svg viewBox="0 0 16 16">
          <circle cx="8" cy="3" r="1.6" />
          <circle cx="3" cy="12" r="1.6" />
          <circle cx="13" cy="12" r="1.6" />
          <path d="M8 4.6v3M8 7.6 4 10.6M8 7.6l4 3" />
        </svg>
        Arrange
      </button>
      <button
        type="button"
        id="coverage"
        title="Colour cells by data coverage (C)"
        aria-pressed={st.s.COVERAGE}
        onClick={() => st.toggleCoverage()}
      >
        <svg viewBox="0 0 16 16">
          <circle cx="8" cy="8" r="6" />
          <path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor" stroke="none" opacity=".6" />
        </svg>
        Coverage
      </button>
      <button
        type="button"
        id="finalise"
        title="Play every scene and approve everything, instantly"
        disabled={st.ui.finalising}
        onClick={() => void finaliseAll()}
      >
        <svg viewBox="0 0 16 16">
          <path d="M2 8.5l4 4 8-9" />
        </svg>
        {st.ui.finalising ? 'Building…' : 'Finalise all'}
      </button>
      <button type="button" id="skip" title="Skip animations (S)" aria-pressed={st.s.SKIP} onClick={() => st.toggleSkip()}>
        <svg viewBox="0 0 16 16">
          <path d="M3 3l6 5-6 5zM11 3v10" />
        </svg>
        {st.s.SKIP ? 'Animations off' : 'Skip animation'}
      </button>
    </div>
  );
}
