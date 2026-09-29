/**
 * The tool row above the teach bar. Markup from reference/ontaix-studio-reference.html lines
 * 194-201 without the Finalise all button; behaviours from lines 548-565 (arrange, coverage,
 * skip), 616 (add a company) and 904-906 (import, drag and drop). The file is read with the
 * mode checked in `#imMode`.
 */
import { useEffect, useRef } from 'react';

import { openAddCompany } from './AddCompany';
import { useStore } from './dom';
import { IMPORT_ACCEPT, ImportModeRows, importFile } from './ImportMode';

export function Tools() {
  const st = useStore();
  const settings = st.ui.settings;
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const over = (e: DragEvent) => e.preventDefault();
    const drop = (e: DragEvent) => {
      e.preventDefault();
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) importFile(f);
    };
    addEventListener('dragover', over);
    addEventListener('drop', drop);
    return () => {
      removeEventListener('dragover', over);
      removeEventListener('drop', drop);
    };
  }, []);

  return (
    <div className="tools" id="tools">
      <button
        type="button"
        id="addCo"
        title="Add another company to the same view"
        style={{ display: settings && !settings.multiCompany ? 'none' : undefined }}
        onClick={openAddCompany}
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
        disabled={st.ui.importing}
        onClick={() => file.current?.click()}
      >
        <svg viewBox="0 0 16 16">
          <path d="M8 2v8M4.5 6.5 8 10l3.5-3.5M3 13h10" />
        </svg>
        {st.ui.importing ? 'Importing…' : 'Import'}
      </button>
      <input
        type="file"
        id="importFile"
        accept={IMPORT_ACCEPT}
        hidden
        ref={file}
        onChange={(e) => {
          const f = e.currentTarget.files?.[0];
          e.currentTarget.value = '';
          if (f) importFile(f);
        }}
      />
      <ImportModeRows />
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
      <button type="button" id="skip" title="Skip animations (S)" aria-pressed={st.s.SKIP} onClick={() => st.toggleSkip()}>
        <svg viewBox="0 0 16 16">
          <path d="M3 3l6 5-6 5zM11 3v10" />
        </svg>
        {st.s.SKIP ? 'Animations off' : 'Skip animation'}
      </button>
    </div>
  );
}
