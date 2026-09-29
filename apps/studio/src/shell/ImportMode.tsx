/**
 * How the next imported document is read: `#imMode`, two `.chk` radio rows beside the Import
 * button. Sentence by sentence is the default and the reference's path; Import, the I key and a
 * dropped file read the file with the mode checked here.
 */
import { useState } from 'react';

import type { ImportMode } from '../teach/teach';
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

export function ImportModeRows() {
  const [mode, setMode] = useState<ImportMode>(chosen);
  return (
    <div id="imMode" ref={refStyle('display:grid;gap:8px')}>
      {IMPORT_MODES.map((row) => (
        <label className="chk" key={row.mode}>
          <input
            type="radio"
            name="imMode"
            value={row.mode}
            checked={row.mode === mode}
            onChange={() => {
              chosen = row.mode;
              setMode(row.mode);
            }}
          />
          <span>
            <b>{row.title}</b>
            <small>{row.detail}</small>
          </span>
        </label>
      ))}
    </div>
  );
}
