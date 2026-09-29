/**
 * How the next imported document is read: one `.tools` pill, `#imMode`, beside Import, in the
 * style and `aria-pressed` pattern of Coverage and Skip. Each click moves to the next mode and
 * the label names the current one; Sentences is the default and the reference's path, and the
 * pill is pressed for any other mode. It is hidden with Import when document import is off. Import, the I key and a dropped file read the file with the
 * current mode.
 */
import { useState } from 'react';

import type { ImportMode } from '../teach/teach';

interface ModeLabel {
  mode: ImportMode;
  label: string;
}

/** The reading modes in cycle order; the first is the default. */
export const IMPORT_MODES: ModeLabel[] = [
  { mode: 'sentences', label: 'Sentences' },
  { mode: 'document', label: 'Whole document' },
  { mode: 'ontology', label: 'Ontology' },
];

let chosen: ImportMode = IMPORT_MODES[0].mode;

/** The mode the next picked or dropped file is read with. */
export const importMode = (): ImportMode => chosen;

/** The mode after `mode` in the cycle. */
export function nextImportMode(mode: ImportMode): ImportMode {
  const at = IMPORT_MODES.findIndex((m) => m.mode === mode);
  return IMPORT_MODES[(at + 1) % IMPORT_MODES.length].mode;
}

export function ImportModePill({ hidden }: { hidden: boolean }) {
  const [mode, setMode] = useState<ImportMode>(chosen);
  const label = IMPORT_MODES.find((m) => m.mode === mode)?.label ?? IMPORT_MODES[0].label;
  return (
    <button
      type="button"
      id="imMode"
      title="How the next imported document is read"
      style={{ display: hidden ? 'none' : undefined }}
      aria-pressed={mode !== IMPORT_MODES[0].mode}
      onClick={() => {
        chosen = nextImportMode(mode);
        setMode(chosen);
      }}
    >
      <svg viewBox="0 0 16 16">
        <path d="M3 4h10M3 8h10M3 12h6" />
      </svg>
      {label}
    </button>
  );
}
