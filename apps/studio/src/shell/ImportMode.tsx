/**
 * How the next imported file is read: `#imMode`, `.chk` radio rows beside the Import button.
 * Sentence by sentence is the default and the reference's path; Ontology maps an ontology or
 * hierarchy file into a tree of proposals. Import, the I key and a dropped file read the file
 * with the mode checked here.
 */
import { useState } from 'react';

import { importOntology } from '../teach/ontology';
import { importDocument } from '../teach/teach';
import { refStyle } from './dom';

export type ImportMode = 'sentences' | 'ontology';

interface ModeRow {
  mode: ImportMode;
  title: string;
  detail: string;
}

/** Every document type of the import and every ontology format. */
export const IMPORT_ACCEPT =
  '.txt,.md,.csv,.json,.docx,.pdf,.pptx,.xlsx,.html,.htm,.owl,.owx,.rdf,.xml,.ttl,.nt,.jsonld,.obo';

/** The reading modes offered, in order; the first is the default. */
export const IMPORT_MODES: ModeRow[] = [
  { mode: 'sentences', title: 'Sentence by sentence', detail: 'Each sentence is taught on its own' },
  {
    mode: 'ontology',
    title: 'Ontology',
    detail: 'OWL, SKOS, OBO, or a CSV or Excel hierarchy, mapped into a tree of proposals',
  },
];

let chosen: ImportMode = IMPORT_MODES[0].mode;

/** The mode the next picked or dropped file is read with. */
export const importMode = (): ImportMode => chosen;

/** Reads a picked or dropped file with the checked mode. */
export function importFile(file: File | null | undefined): void {
  if (chosen === 'ontology') void importOntology(file);
  else void importDocument(file);
}

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
