/**
 * How the last imported file was read, and the choice of another reading: one `.tools` pill,
 * `#imAs`, beside Import, shown once a file has been imported and hidden with Import when
 * document import is off. Its label is the current reading; a click opens the reference's small
 * `dialog()` with a `.form` select of every reading, as the reference's Bind dialog does, and
 * `Import again` imports the same file read the chosen way.
 */
import { t, useT } from '../i18n/i18n';
import { store } from '../store/store';
import { importAgain } from '../teach/importFile';
import { detectedReading, READINGS, readingLabel, type ImportReading } from '../teach/importReading';
import { refStyle, useStore } from './dom';

/** Every document type of the import and every ontology format, for the file picker. */
export const IMPORT_ACCEPT =
  '.txt,.md,.csv,.json,.docx,.pdf,.pptx,.xlsx,.html,.htm,.owl,.owx,.rdf,.xml,.ttl,.nt,.jsonld,.obo';

export function ImportAsPill({ hidden }: { hidden: boolean }) {
  const st = useStore();
  const t = useT();
  const last = st.ui.lastImport;
  if (!last) return null;
  return (
    <button
      type="button"
      id="imAs"
      title={t('shell.importAs.pillTitle', { file: last.file.name })}
      style={{ display: hidden ? 'none' : undefined }}
      disabled={st.ui.importing}
      onClick={openImportAs}
    >
      <svg viewBox="0 0 16 16">
        <path d="M3 4h10M3 8h10M3 12h6" />
      </svg>
      {t('shell.importAs.readAs', { reading: readingLabel(last.reading) })}
    </button>
  );
}

export function openImportAs(): void {
  const last = store.ui.lastImport;
  if (!last) return;
  store.openDialog({
    title: t('shell.importAs.title', { file: last.file.name }),
    small: true,
    body: (
      <div className="form" ref={refStyle('grid-template-columns:90px 1fr')}>
        <label>{t('shell.importAs.label')}</label>
        <select id="imAsRead" defaultValue={last.reading}>
          {READINGS.map((r) => (
            <option key={r.reading} value={r.reading}>
              {r.label}
            </option>
          ))}
        </select>
        <label></label>
        <small ref={refStyle('color:var(--ink-3)')}>
          {t('shell.importAs.detected', { reading: readingLabel(detectedReading(last.detection)) })}
        </small>
      </div>
    ),
    buttons: [
      { label: t('common.cancel') },
      {
        label: t('shell.importAs.importAgain'),
        cls: 'primary',
        onClick: (bk) => {
          const chosen = bk.querySelector<HTMLSelectElement>('#imAsRead')?.value as ImportReading | undefined;
          if (chosen) void importAgain(chosen);
        },
      },
    ],
  });
}
