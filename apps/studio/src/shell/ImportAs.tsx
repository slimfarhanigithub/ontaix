/**
 * How the last imported file was read, and the choice of another reading: one `.tools` pill,
 * `#imAs`, beside Import, shown once a file has been imported and hidden with Import when
 * document import is off. Its label is the current reading; a click opens the reference's small
 * `dialog()` with a `.form` select of every reading, as the reference's Bind dialog does, and
 * `Import again` imports the same file read the chosen way.
 */
import { store } from '../store/store';
import { importAgain } from '../teach/importFile';
import { detectedReading, READINGS, readingLabel, type ImportReading } from '../teach/importReading';
import { refStyle, useStore } from './dom';

/** Every document type of the import and every ontology format, for the file picker. */
export const IMPORT_ACCEPT =
  '.txt,.md,.csv,.json,.docx,.pdf,.pptx,.xlsx,.html,.htm,.owl,.owx,.rdf,.xml,.ttl,.nt,.jsonld,.obo';

export function ImportAsPill({ hidden }: { hidden: boolean }) {
  const st = useStore();
  const last = st.ui.lastImport;
  if (!last) return null;
  return (
    <button
      type="button"
      id="imAs"
      title={`Read ${last.file.name} another way`}
      style={{ display: hidden ? 'none' : undefined }}
      disabled={st.ui.importing}
      onClick={openImportAs}
    >
      <svg viewBox="0 0 16 16">
        <path d="M3 4h10M3 8h10M3 12h6" />
      </svg>
      Read as: {readingLabel(last.reading)}
    </button>
  );
}

export function openImportAs(): void {
  const last = store.ui.lastImport;
  if (!last) return;
  store.openDialog({
    title: `Read ${last.file.name} as`,
    small: true,
    body: (
      <div className="form" ref={refStyle('grid-template-columns:90px 1fr')}>
        <label>Read as</label>
        <select id="imAsRead" defaultValue={last.reading}>
          {READINGS.map((r) => (
            <option key={r.reading} value={r.reading}>
              {r.label}
            </option>
          ))}
        </select>
        <label></label>
        <small ref={refStyle('color:var(--ink-3)')}>
          {`Detected as ${readingLabel(detectedReading(last.detection))}. The file is imported again, read the way chosen.`}
        </small>
      </div>
    ),
    buttons: [
      { label: 'Cancel' },
      {
        label: 'Import again',
        cls: 'primary',
        onClick: (bk) => {
          const chosen = bk.querySelector<HTMLSelectElement>('#imAsRead')?.value as ImportReading | undefined;
          if (chosen) void importAgain(chosen);
        },
      },
    ],
  });
}
