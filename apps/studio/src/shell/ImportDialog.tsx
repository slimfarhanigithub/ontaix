/**
 * The import dialog: how the next document is read, chosen as `.chk` radio rows in `#imMode`,
 * then the file picker. An owner addition absent from the reference, whose Import button opens
 * the picker directly; sentence by sentence stays the default and is the reference's path.
 */
import type { ImportMode } from '../teach/teach';
import { store } from '../store/store';
import { refStyle } from './dom';

interface ModeRow {
  mode: ImportMode;
  title: string;
  detail: string;
}

/** The reading modes offered, in order; the first is the default. */
export const IMPORT_MODES: ModeRow[] = [
  { mode: 'sentences', title: 'Sentence by sentence', detail: 'Each sentence is taught on its own' },
  { mode: 'document', title: 'Whole document', detail: 'The model maps the whole document into one tree of proposals' },
];

let chosen: ImportMode = IMPORT_MODES[0].mode;

/** The mode the next picked or dropped file is read with. */
export const importMode = (): ImportMode => chosen;

export function openImportDialog(): void {
  store.openDialog({
    title: 'Import a document',
    sub: 'detect concepts and relations',
    body: (
      <div className="form">
        <label>Read it</label>
        <div id="imMode" ref={refStyle('display:grid;gap:8px')}>
          {IMPORT_MODES.map((row) => (
            <label className="chk" key={row.mode}>
              <input type="radio" name="imMode" value={row.mode} defaultChecked={row.mode === chosen} />
              <span>
                <b>{row.title}</b>
                <small>{row.detail}</small>
              </span>
            </label>
          ))}
        </div>
      </div>
    ),
    buttons: [
      { label: 'Cancel' },
      {
        label: 'Choose a file',
        cls: 'primary',
        onClick: (bk) => {
          const value = bk.querySelector<HTMLInputElement>('input[name=imMode]:checked')?.value;
          chosen = IMPORT_MODES.find((row) => row.mode === value)?.mode ?? IMPORT_MODES[0].mode;
          (document.getElementById('importFile') as HTMLInputElement | null)?.click();
        },
      },
    ],
  });
}
